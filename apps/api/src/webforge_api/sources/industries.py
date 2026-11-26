"""Industry vocabulary shared by campaigns, website evidence and the design engine."""

from __future__ import annotations

INDUSTRIES: dict[str, str] = {
    "dental": "Dental clinics",
    "healthcare": "Clinics and healthcare",
    "restaurant": "Restaurants and cafes",
    "bakery": "Bakeries",
    "hospitality": "Hotels and guest houses",
    "legal": "Law firms",
    "retail": "Shops and retail",
    "automotive": "Automotive services",
    "real_estate": "Real estate",
    "home_services": "Home and construction services",
    "beauty": "Salons and beauty",
    "education": "Schools and training",
    "finance": "Accounting and finance",
    "fitness": "Gyms and fitness",
    "professional_services": "Professional services",
    "manufacturing": "Manufacturing",
}

# schema.org @type (lower-case) -> industry key. Only the business's own structured data is used.
SCHEMA_TYPE_INDUSTRY: dict[str, str] = {
    "dentist": "dental",
    "medicalclinic": "healthcare",
    "physician": "healthcare",
    "medicalbusiness": "healthcare",
    "hospital": "healthcare",
    "restaurant": "restaurant",
    "foodestablishment": "restaurant",
    "cafeorcoffeeshop": "restaurant",
    "bakery": "bakery",
    "hotel": "hospitality",
    "lodgingbusiness": "hospitality",
    "legalservice": "legal",
    "attorney": "legal",
    "store": "retail",
    "clothingstore": "retail",
    "automotivebusiness": "automotive",
    "autorepair": "automotive",
    "realestateagent": "real_estate",
    "homeandconstructionbusiness": "home_services",
    "plumber": "home_services",
    "electrician": "home_services",
    "healthandbeautybusiness": "beauty",
    "beautysalon": "beauty",
    "hairsalon": "beauty",
    "educationalorganization": "education",
    "school": "education",
    "accountingservice": "finance",
    "financialservice": "finance",
    "exercisegym": "fitness",
    "sportsactivitylocation": "fitness",
    "professionalservice": "professional_services",
}


def industry_from_schema_types(types: list[str]) -> str | None:
    for t in types:
        industry = SCHEMA_TYPE_INDUSTRY.get(t.lower())
        if industry:
            return industry
    return None
