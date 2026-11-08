from pydantic import BaseModel


class Product(BaseModel):
    source: str
    name: str
    price: str | None = None
    url: str
    image: str | None = None


class SourceResult(BaseModel):
    source: str
    search_url: str
    ok: bool
    error: str | None = None
    products: list[Product] = []


class Vendor(BaseModel):
    id: str
    name: str
    kind: str
    lat: float
    lon: float
    address: str = ""
    website: str | None = None
    phone: str | None = None
    hours: str | None = None
    km: float
    minutes: int
    minutes_source: str = "estimate"


class VendorHit(BaseModel):
    vendor: Vendor
    search_url: str
    products: list[Product]
