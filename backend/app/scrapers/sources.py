from .base import Source

# Online shops searched live. JSON-LD is the default parser; add CSS selectors
# per source (item_selector, name_selector, price_selector) once verified.
SOURCES: list[Source] = [
    Source(
        name="Waitrose",
        search_url="https://www.waitrose.com/ecom/shop/search?searchTerm={q}",
        base_url="https://www.waitrose.com",
        use_browser=False,  # tested: still blocked in headless Chromium
    ),
    Source(
        name="Tesco",
        search_url="https://www.tesco.com/groceries/en-GB/search?query={q}",
        base_url="https://www.tesco.com",
        use_browser=False,  # tested: still blocked in headless Chromium
    ),
    Source(
        name="Sainsbury's",
        search_url="https://www.sainsburys.co.uk/gol-ui/SearchResults/{q}",
        base_url="https://www.sainsburys.co.uk",
        use_browser=False,  # tested: still blocked in headless Chromium
    ),
    Source(
        name="Abel & Cole",
        search_url="https://www.abelandcole.co.uk/shop/search?term={q}",
        base_url="https://www.abelandcole.co.uk",
        item_selector="article[class*=productCard]",
        name_selector="a[class*=productTitleLink]",
        link_selector="a[class*=productTitleLink]",
        price_selector="[class*=productPrice]",
    ),
    Source(
        name="Riverford",
        search_url="https://www.riverford.co.uk/search?q={q}",
        base_url="https://www.riverford.co.uk",
        item_selector='a[href*="/shop/products/"]',
    ),
    Source(
        name="Planet Organic",
        search_url="https://www.planetorganic.com/search?q={q}",
        base_url="https://www.planetorganic.com",
        item_selector='a[href*="/products/"]',
    ),
    Source(
        name="Farmdrop",
        search_url="https://www.farmdrop.com/search?q={q}",
        base_url="https://www.farmdrop.com",
        item_selector='a[href*="/products/"]',
    ),
    Source(
        name="Caley Brothers (grow kits)",
        search_url="https://www.caleybrothers.co.uk/search?q={q}",
        base_url="https://www.caleybrothers.co.uk",
        item_selector='a[href*="/products/"]',
    ),
    Source(
        name="Garsons Farm Shop",
        search_url="https://www.garsons.co.uk/search?q={q}",
        base_url="https://www.garsons.co.uk",
    ),
]
