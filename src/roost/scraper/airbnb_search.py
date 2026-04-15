"""Airbnb search scraper using Playwright GraphQL interception.

Intercepts Airbnb's StaysSearch GraphQL API responses rather than parsing
the DOM, since Airbnb hashes CSS class names on every deploy.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from dataclasses import asdict
from urllib.parse import quote, urlencode

from playwright.async_api import Page, Response, async_playwright

from roost.models import AirbnbComp

logger = logging.getLogger(__name__)

# Stealth browser settings
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
VIEWPORT = {"width": 1920, "height": 1080}


def _build_search_url(
    location: str,
    checkin: str,
    checkout: str,
    guests: int,
    min_bedrooms: int,
) -> str:
    """Build an Airbnb search URL with the given filters.

    Args:
        location: Free-text location string (e.g. "Downtown Traverse City, MI").
        checkin: Check-in date as YYYY-MM-DD.
        checkout: Checkout date as YYYY-MM-DD.
        guests: Number of adult guests.
        min_bedrooms: Minimum bedroom count filter.
    """
    params = {
        "query": location,
        "checkin": checkin,
        "checkout": checkout,
        "adults": str(guests),
        "min_bedrooms": str(min_bedrooms),
        "search_type": "filter_change",
    }
    return f"https://www.airbnb.com/s/{quote(location)}/homes?{urlencode(params)}"


def _dollars_to_cents(amount: float | int | str) -> int:
    """Convert a dollar amount (possibly string like '$123') to integer cents."""
    if isinstance(amount, str):
        amount = amount.replace("$", "").replace(",", "").strip()
    return int(round(float(amount) * 100))


def _safe_get(data: dict, *keys, default=None):
    """Safely traverse nested dicts/lists without KeyError."""
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list) and isinstance(key, int) and key < len(current):
            current = current[key]
        else:
            return default
        if current is None:
            return default
    return current


def _parse_listing_from_graphql(result: dict) -> AirbnbComp | None:
    """Extract an AirbnbComp from a single StaysSearch result node.

    Airbnb's GraphQL schema nests listing data under several possible
    paths depending on API version. This function tries the known
    structures and gracefully returns None on parse failure.
    """
    try:
        listing = _safe_get(result, "listing") or {}
        pricing = _safe_get(result, "pricingQuote") or _safe_get(result, "pricing") or {}

        listing_id = str(
            listing.get("id")
            or _safe_get(result, "listingId")
            or listing.get("listingId", "")
        )
        if not listing_id:
            return None

        title = listing.get("title") or listing.get("name") or ""

        # Property type
        property_type = (
            _safe_get(listing, "roomTypeCategory")
            or _safe_get(listing, "typeOfPlace")
            or _safe_get(listing, "listingObjType")
            or ""
        )

        # Bedrooms and capacity
        bedrooms = _safe_get(listing, "bedrooms") or 0
        capacity = _safe_get(listing, "personCapacity") or _safe_get(listing, "guestCapacity") or 0

        # Pricing -- Airbnb returns structured price objects
        nightly_price_cents = 0
        total_price_cents = 0

        # Try structured price path first
        price_obj = (
            _safe_get(pricing, "price", "total")
            or _safe_get(pricing, "price")
            or _safe_get(pricing, "rate", "amount")
            or {}
        )
        if isinstance(price_obj, dict):
            raw_total = price_obj.get("amount") or price_obj.get("amountFormatted")
            if raw_total is not None:
                total_price_cents = _dollars_to_cents(raw_total)

        rate_obj = (
            _safe_get(pricing, "rate", "amount")
            or _safe_get(pricing, "price", "rate", "amount")
            or _safe_get(pricing, "rateWithServiceFee", "amount")
            or _safe_get(pricing, "priceString")
        )
        if rate_obj is not None:
            nightly_price_cents = _dollars_to_cents(rate_obj)

        # Fallback: try structured price items for nightly / total
        structured_price = _safe_get(pricing, "structuredStayDisplayPrice", "primaryLine") or {}
        if not nightly_price_cents:
            price_str = structured_price.get("price") or structured_price.get("discountedPrice") or ""
            if price_str:
                nightly_price_cents = _dollars_to_cents(price_str)

        secondary_line = _safe_get(pricing, "structuredStayDisplayPrice", "secondaryLine") or {}
        if not total_price_cents:
            total_str = secondary_line.get("price") or ""
            if total_str:
                total_price_cents = _dollars_to_cents(total_str)

        # Rating and reviews
        rating = _safe_get(listing, "avgRating") or _safe_get(listing, "avgRatingA11yLabel")
        if isinstance(rating, str):
            # Parse from "4.92 out of 5" style
            try:
                rating = float(rating.split()[0])
            except (ValueError, IndexError):
                rating = None
        review_count = _safe_get(listing, "reviewsCount") or _safe_get(listing, "reviews_count") or 0

        # Superhost
        superhost = bool(
            _safe_get(listing, "isSuperhost")
            or _safe_get(listing, "host", "isSuperhost")
        )

        # Coordinates
        lat = _safe_get(listing, "coordinate", "latitude") or _safe_get(listing, "lat")
        lng = _safe_get(listing, "coordinate", "longitude") or _safe_get(listing, "lng")

        # Amenities (often not present in search results, but try)
        amenities_raw = _safe_get(listing, "amenities") or []
        amenities: list[str] = []
        if isinstance(amenities_raw, list):
            for a in amenities_raw:
                if isinstance(a, str):
                    amenities.append(a)
                elif isinstance(a, dict):
                    amenities.append(a.get("name", ""))

        url = f"https://www.airbnb.com/rooms/{listing_id}"

        return AirbnbComp(
            listing_id=listing_id,
            title=title,
            property_type=str(property_type),
            bedrooms=int(bedrooms),
            capacity=int(capacity),
            nightly_price_cents=nightly_price_cents,
            total_price_cents=total_price_cents,
            rating=float(rating) if rating else None,
            review_count=int(review_count),
            superhost=superhost,
            latitude=float(lat) if lat else None,
            longitude=float(lng) if lng else None,
            amenities=amenities,
            url=url,
        )
    except Exception:
        logger.debug("Failed to parse listing from GraphQL result", exc_info=True)
        return None


async def _parse_dom_fallback(page: Page) -> list[AirbnbComp]:
    """Fallback DOM-based parsing when GraphQL interception yields nothing.

    Uses the data-testid='card-container' selector which is more stable
    than hashed class names.
    """
    logger.info("Attempting DOM fallback parse")
    comps: list[AirbnbComp] = []

    cards = await page.query_selector_all('[data-testid="card-container"]')
    logger.info(f"DOM fallback found {len(cards)} card containers")

    for card in cards:
        try:
            link_el = await card.query_selector("a[href*='/rooms/']")
            if not link_el:
                continue
            href = await link_el.get_attribute("href") or ""
            # Extract listing ID from href like /rooms/12345?...
            listing_id = ""
            if "/rooms/" in href:
                listing_id = href.split("/rooms/")[1].split("?")[0].split("/")[0]
            if not listing_id:
                continue

            title_el = await card.query_selector('[data-testid="listing-card-title"]')
            title = (await title_el.inner_text()).strip() if title_el else ""

            # Subtitle often contains "Entire home", "2 bedrooms", "4 guests" etc.
            property_type = ""
            bedrooms = 0
            capacity = 0
            subtitle_el = await card.query_selector('[data-testid="listing-card-subtitle"]')
            if not subtitle_el:
                # Try getting all text spans under the card for metadata
                subtitle_el = await card.query_selector('[data-testid="listing-card-name"]')
            if subtitle_el:
                subtitle_parts = (await subtitle_el.inner_text()).strip().split("\n")
                subtitle_text = " ".join(subtitle_parts).lower()
                # Extract property type
                for ptype in ["entire home", "entire condo", "entire cottage", "entire cabin",
                              "entire townhouse", "entire villa", "entire guest", "private room",
                              "entire rental", "entire place", "entire loft", "entire bungalow"]:
                    if ptype in subtitle_text:
                        property_type = ptype.replace("entire ", "")
                        break
                # Extract bedrooms: "2 bedrooms" or "2 beds"
                br_match = re.search(r"(\d+)\s*bedroom", subtitle_text)
                if br_match:
                    bedrooms = int(br_match.group(1))
                # Extract guests: "4 guests"
                guest_match = re.search(r"(\d+)\s*guest", subtitle_text)
                if guest_match:
                    capacity = int(guest_match.group(1))

            # Also check the card text blob for bedroom/guest info if subtitle didn't have it
            if not bedrooms or not capacity:
                card_text = (await card.inner_text()).lower()
                if not bedrooms:
                    br_match = re.search(r"(\d+)\s*bedroom", card_text)
                    if br_match:
                        bedrooms = int(br_match.group(1))
                if not capacity:
                    guest_match = re.search(r"(\d+)\s*guest", card_text)
                    if guest_match:
                        capacity = int(guest_match.group(1))

            # Price -- look for the displayed price
            price_el = await card.query_selector('span._1y74zjx, [data-testid="price-availability-row"] span')
            nightly_price_cents = 0
            if price_el:
                price_text = await price_el.inner_text()
                price_match = re.search(r"\$[\d,]+", price_text)
                if price_match:
                    nightly_price_cents = _dollars_to_cents(price_match.group())

            # If no price from specific selectors, scan all spans for a dollar amount
            if not nightly_price_cents:
                all_spans = await card.query_selector_all("span")
                for span in all_spans:
                    span_text = await span.inner_text()
                    price_match = re.search(r"\$[\d,]+", span_text)
                    if price_match:
                        nightly_price_cents = _dollars_to_cents(price_match.group())
                        break

            # Rating
            rating = None
            review_count = 0
            rating_el = await card.query_selector('[aria-label*="rating"]')
            if rating_el:
                rating_text = await rating_el.get_attribute("aria-label") or ""
                rating_match = re.search(r"([\d.]+)\s*out of\s*5", rating_text)
                if rating_match:
                    rating = float(rating_match.group(1))
                review_match = re.search(r"(\d+)\s*review", rating_text)
                if review_match:
                    review_count = int(review_match.group(1))

            # Superhost badge
            superhost = False
            superhost_el = await card.query_selector('[aria-label*="Superhost"], [aria-label*="superhost"]')
            if superhost_el:
                superhost = True

            comps.append(AirbnbComp(
                listing_id=listing_id,
                title=title,
                property_type=property_type,
                bedrooms=bedrooms,
                capacity=capacity,
                nightly_price_cents=nightly_price_cents,
                total_price_cents=0,
                rating=rating,
                review_count=review_count,
                superhost=superhost,
                url=f"https://www.airbnb.com/rooms/{listing_id}",
            ))
        except Exception:
            logger.debug("DOM fallback: failed to parse a card", exc_info=True)
            continue

    return comps


async def scrape_search(
    location: str,
    checkin: str,
    checkout: str,
    guests: int,
    min_bedrooms: int,
    max_pages: int = 3,
) -> list[AirbnbComp]:
    """Scrape Airbnb search results for competing listings.

    Args:
        location: Free-text location (e.g. "Downtown Traverse City, MI").
        checkin: Check-in date as YYYY-MM-DD.
        checkout: Checkout date as YYYY-MM-DD.
        guests: Number of adult guests.
        min_bedrooms: Minimum bedroom filter.
        max_pages: Maximum number of result pages to scrape.

    Returns:
        List of AirbnbComp dataclass instances.
    """
    comps: list[AirbnbComp] = []
    captured_responses: list[dict] = []

    async def _handle_response(response: Response) -> None:
        """Listener that captures StaysSearch GraphQL responses."""
        url = response.url
        if "StaysSearch" not in url:
            return
        try:
            body = await response.json()
            captured_responses.append(body)
            logger.debug(f"Captured StaysSearch response ({len(captured_responses)} total)")
        except Exception:
            logger.debug("Failed to parse StaysSearch response body", exc_info=True)

    search_url = _build_search_url(location, checkin, checkout, guests, min_bedrooms)
    logger.info(f"Starting Airbnb search: {search_url}")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport=VIEWPORT,
            locale="en-US",
        )

        # Stealth: mask webdriver flag
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => false,
            });
        """)

        page = await context.new_page()
        page.on("response", _handle_response)

        for page_num in range(1, max_pages + 1):
            logger.info(f"Loading page {page_num}/{max_pages}")

            if page_num == 1:
                await page.goto(search_url, wait_until="domcontentloaded", timeout=60_000)
                # Wait for search results to render (or a "no results" indicator)
                try:
                    await page.wait_for_selector(
                        '[data-testid="card-container"], [data-testid="listing-card-title"], '
                        '[itemprop="itemListElement"], [data-testid="no-results-message"]',
                        timeout=15_000,
                    )
                except Exception:
                    logger.warning("Timed out waiting for search result cards to appear")
                # Give GraphQL responses a moment to arrive
                await asyncio.sleep(3)
            else:
                # Paginate: scroll to bottom and click Next
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(1)

                next_button = await page.query_selector('a[aria-label="Next"], a[data-testid="pagination-next"]')
                if not next_button:
                    logger.info(f"No 'Next' button found on page {page_num - 1}, stopping pagination")
                    break

                await next_button.click()
                try:
                    await page.wait_for_selector(
                        '[data-testid="card-container"], [itemprop="itemListElement"]',
                        timeout=15_000,
                    )
                except Exception:
                    logger.warning(f"Timeout waiting for page {page_num} results")
                await asyncio.sleep(2)

            # Random delay between pages to look human
            if page_num < max_pages:
                delay = random.uniform(3.0, 7.0)
                logger.debug(f"Waiting {delay:.1f}s before next action")
                await asyncio.sleep(delay)

        # Parse captured GraphQL responses
        for response_body in captured_responses:
            search_results = _safe_get(
                response_body,
                "data", "presentation", "staysSearch", "results", "searchResults",
            ) or []

            if not search_results:
                # Try alternate response structure
                search_results = _safe_get(
                    response_body,
                    "data", "presentation", "explore", "sections", "sectionIndependentData",
                    "staysSearch", "searchResults",
                ) or []

            logger.debug(f"Parsing {len(search_results)} results from a StaysSearch response")
            for result in search_results:
                comp = _parse_listing_from_graphql(result)
                if comp:
                    comps.append(comp)

        # Deduplicate by listing_id
        seen_ids: set[str] = set()
        unique_comps: list[AirbnbComp] = []
        for comp in comps:
            if comp.listing_id not in seen_ids:
                seen_ids.add(comp.listing_id)
                unique_comps.append(comp)
        comps = unique_comps

        logger.info(f"GraphQL interception yielded {len(comps)} unique listings")

        # Fallback to DOM parsing if GraphQL gave us nothing
        if not comps:
            logger.warning("GraphQL interception returned 0 results, falling back to DOM parsing")
            comps = await _parse_dom_fallback(page)
            logger.info(f"DOM fallback yielded {len(comps)} listings")

        await browser.close()

    logger.info(f"Scrape complete: {len(comps)} comps for '{location}'")
    return comps


def comps_to_dicts(comps: list[AirbnbComp]) -> list[dict]:
    """Convert a list of AirbnbComp instances to plain dicts for JSON serialization."""
    return [asdict(c) for c in comps]
