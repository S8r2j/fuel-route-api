import csv
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand
from django.db import transaction

from stations.models import FuelStation

class Command(BaseCommand):
    help = "Load fuel stations from the fuel prices CSV"

    def add_arguments(self, parser):
        parser.add_argument("csv_path")

    def handle(self, *args, **opts):
        stations = {}
        skipped = 0

        with open(opts["csv_path"], newline="", encoding="utf-8-sig") as f: # encoding strips the invisible characters that we might get when importing csv
            for row in csv.DictReader(f):
                try:
                    opis_id = int(row["OPIS Truckstop ID"])
                    price = Decimal(row["Retail Price"]).quantize(Decimal("0.001")) # rounding the decimal to 3 places
                except (ValueError, InvalidOperation, KeyError):
                    skipped += 1
                    continue
                
                # Same stations listed twice: keeping the cheaper row
                existing = stations.get(opis_id)
                if existing and existing.price <= price:
                    continue

                rack_id = row["Rack ID"].strip()
                stations[opis_id] = FuelStation(
                    opis_id=opis_id,
                    name=row["Truckstop Name"].strip(),
                    address=row["Address"].strip(),
                    city=row["City"].strip(),
                    state=row["State"].strip(),
                    rack_id=int(rack_id) if rack_id else None,
                    price=price
                )
        
        with transaction.atomic():
            FuelStation.objects.all().delete()
            FuelStation.objects.bulk_create(stations.values(), batch_size=1000)

        self.stdout.write(self.style.SUCCESS(
            f"Loaded {len(stations)} stations, skipped {skipped} rows"
        ))