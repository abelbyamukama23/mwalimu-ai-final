"""Django management command to seed standard geographic units for Mwalimu context resolution."""

from django.core.management.base import BaseCommand
from platform_api.apps.context.models import GeographicUnit, GeographicUnitStatus, GeographicUnitType


class Command(BaseCommand):
    help = "Seed standard geographic units across East Africa and Africa for familiar region resolution."

    def handle(self, *args, **options):
        self.stdout.write("Seeding Geographic Units...")

        # 1. Countries
        countries = [
            {"name": "Uganda", "slug": "uganda", "country_code": "UG", "unit_type": GeographicUnitType.COUNTRY, "tags": ["east-africa", "great-lakes"]},
            {"name": "Kenya", "slug": "kenya", "country_code": "KE", "unit_type": GeographicUnitType.COUNTRY, "tags": ["east-africa"]},
            {"name": "Tanzania", "slug": "tanzania", "country_code": "TZ", "unit_type": GeographicUnitType.COUNTRY, "tags": ["east-africa", "swahili"]},
            {"name": "Rwanda", "slug": "rwanda", "country_code": "RW", "unit_type": GeographicUnitType.COUNTRY, "tags": ["east-africa", "great-lakes"]},
            {"name": "Nigeria", "slug": "nigeria", "country_code": "NG", "unit_type": GeographicUnitType.COUNTRY, "tags": ["west-africa"]},
            {"name": "Ghana", "slug": "ghana", "country_code": "GH", "unit_type": GeographicUnitType.COUNTRY, "tags": ["west-africa"]},
            {"name": "South Africa", "slug": "south-africa", "country_code": "ZA", "unit_type": GeographicUnitType.COUNTRY, "tags": ["southern-africa"]},
        ]

        created_countries = {}
        for c in countries:
            obj, created = GeographicUnit.objects.get_or_create(
                slug=c["slug"],
                parent=None,
                defaults={
                    "name": c["name"],
                    "country_code": c["country_code"],
                    "unit_type": c["unit_type"],
                    "status": GeographicUnitStatus.ACTIVE,
                    "metadata": {"tags": c["tags"]},
                },
            )
            created_countries[c["country_code"]] = obj
            action = "Created" if created else "Existing"
            self.stdout.write(f"  [{action}] Country: {obj.name}")

        # 2. Districts & Cities
        units = [
            # Uganda
            {"name": "Kampala", "slug": "kampala", "country_code": "UG", "unit_type": GeographicUnitType.CITY, "tags": ["capital", "urban", "central-uganda"]},
            {"name": "Wakiso", "slug": "wakiso", "country_code": "UG", "unit_type": GeographicUnitType.DISTRICT, "tags": ["central-uganda", "lake-victoria"]},
            {"name": "Mukono", "slug": "mukono", "country_code": "UG", "unit_type": GeographicUnitType.DISTRICT, "tags": ["central-uganda", "agriculture"]},
            {"name": "Jinja", "slug": "jinja", "country_code": "UG", "unit_type": GeographicUnitType.CITY, "tags": ["eastern-uganda", "source-of-nile", "industry"]},
            {"name": "Mbarara", "slug": "mbarara", "country_code": "UG", "unit_type": GeographicUnitType.CITY, "tags": ["western-uganda", "cattle-corridor", "dairy"]},
            {"name": "Gulu", "slug": "gulu", "country_code": "UG", "unit_type": GeographicUnitType.CITY, "tags": ["northern-uganda", "acholi"]},
            {"name": "Mbale", "slug": "mbale", "country_code": "UG", "unit_type": GeographicUnitType.CITY, "tags": ["eastern-uganda", "mount-elgon", "coffee"]},
            {"name": "Fort Portal", "slug": "fort-portal", "country_code": "UG", "unit_type": GeographicUnitType.CITY, "tags": ["tourism", "rwenzori", "tea"]},
            {"name": "Arua", "slug": "arua", "country_code": "UG", "unit_type": GeographicUnitType.CITY, "tags": ["west-nile", "tobacco"]},

            # Kenya
            {"name": "Nairobi", "slug": "nairobi", "country_code": "KE", "unit_type": GeographicUnitType.CITY, "tags": ["capital", "urban", "commercial-hub"]},
            {"name": "Mombasa", "slug": "mombasa", "country_code": "KE", "unit_type": GeographicUnitType.CITY, "tags": ["coastal", "port", "swahili"]},
            {"name": "Kisumu", "slug": "kisumu", "country_code": "KE", "unit_type": GeographicUnitType.CITY, "tags": ["lake-victoria", "western-kenya"]},
            {"name": "Nakuru", "slug": "nakuru", "country_code": "KE", "unit_type": GeographicUnitType.CITY, "tags": ["rift-valley", "farming"]},
            {"name": "Kirinyaga", "slug": "kirinyaga", "country_code": "KE", "unit_type": GeographicUnitType.COUNTY, "tags": ["mount-kenya", "rice-mwea", "coffee", "tea"]},
            {"name": "Kiambu", "slug": "kiambu", "country_code": "KE", "unit_type": GeographicUnitType.COUNTY, "tags": ["central-kenya", "coffee", "dairy"]},
            {"name": "Machakos", "slug": "machakos", "country_code": "KE", "unit_type": GeographicUnitType.COUNTY, "tags": ["eastern-kenya", "semi-arid"]},
            {"name": "Uasin Gishu (Eldoret)", "slug": "eldoret", "country_code": "KE", "unit_type": GeographicUnitType.COUNTY, "tags": ["north-rift", "athletics", "maize-breadbasket"]},

            # Tanzania
            {"name": "Dar es Salaam", "slug": "dar-es-salaam", "country_code": "TZ", "unit_type": GeographicUnitType.CITY, "tags": ["coastal", "commercial-capital", "swahili"]},
            {"name": "Arusha", "slug": "arusha", "country_code": "TZ", "unit_type": GeographicUnitType.CITY, "tags": ["northern-tanzania", "safari", "meru"]},
            {"name": "Dodoma", "slug": "dodoma", "country_code": "TZ", "unit_type": GeographicUnitType.CITY, "tags": ["capital", "central-tanzania"]},
            {"name": "Mwanza", "slug": "mwanza", "country_code": "TZ", "unit_type": GeographicUnitType.CITY, "tags": ["lake-victoria", "rock-city", "fishing"]},
            {"name": "Zanzibar", "slug": "zanzibar", "country_code": "TZ", "unit_type": GeographicUnitType.REGION, "tags": ["island", "spices", "coastal"]},

            # Rwanda
            {"name": "Kigali", "slug": "kigali", "country_code": "RW", "unit_type": GeographicUnitType.CITY, "tags": ["capital", "thousand-hills"]},
            {"name": "Musanze", "slug": "musanze", "country_code": "RW", "unit_type": GeographicUnitType.DISTRICT, "tags": ["volcanoes", "tourism", "potatoes"]},
            {"name": "Huye (Butare)", "slug": "huye", "country_code": "RW", "unit_type": GeographicUnitType.DISTRICT, "tags": ["southern-rwanda", "university"]},

            # Nigeria, Ghana, South Africa
            {"name": "Lagos", "slug": "lagos", "country_code": "NG", "unit_type": GeographicUnitType.CITY, "tags": ["commercial-capital", "coastal", "megacity"]},
            {"name": "Abuja", "slug": "abuja", "country_code": "NG", "unit_type": GeographicUnitType.CITY, "tags": ["capital", "federal"]},
            {"name": "Accra", "slug": "accra", "country_code": "GH", "unit_type": GeographicUnitType.CITY, "tags": ["capital", "coastal"]},
            {"name": "Johannesburg", "slug": "johannesburg", "country_code": "ZA", "unit_type": GeographicUnitType.CITY, "tags": ["commercial-hub", "gauteng"]},
            {"name": "Cape Town", "slug": "cape-town", "country_code": "ZA", "unit_type": GeographicUnitType.CITY, "tags": ["coastal", "western-cape"]},
        ]

        count = 0
        for u in units:
            parent = created_countries.get(u["country_code"])
            obj, created = GeographicUnit.objects.get_or_create(
                slug=u["slug"],
                parent=parent,
                defaults={
                    "name": u["name"],
                    "country_code": u["country_code"],
                    "unit_type": u["unit_type"],
                    "status": GeographicUnitStatus.ACTIVE,
                    "metadata": {"tags": u["tags"]},
                },
            )
            count += 1
            action = "Created" if created else "Existing"
            self.stdout.write(f"  [{action}] {u['unit_type'].capitalize()}: {obj.name} ({u['country_code']})")

        self.stdout.write(self.style.SUCCESS(f"Successfully seeded {len(countries)} countries and {count} administrative units!"))
