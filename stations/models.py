from django.db import models

class FuelStation(models.Model):
    opis_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=120)
    state = models.CharField(max_length=2)
    rack_id = models.IntegerField(null=True, blank=True)
    price = models.DecimalField(max_digits=6, decimal_places=3)
    lat = models.FloatField(null=True, blank=True)
    lon = models.FloatField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["state","city"])]

    def __str__(self):
        return f"{self.name} - {self.city}, {self.state} (${self.price})"
    

class CensusPlace(models.Model):
    """
    A town from Census Gazetteer places file.
    
    Saved by geocode_stations to get start & finish
    in coordinates
    """
    state = models.CharField(max_length=2)
    name = models.CharField(max_length=120)
    # key & whole key refers to match level values
    key = models.CharField(max_length=120)
    whole_key = models.CharField(max_length=120)
    lat = models.FloatField()
    lon = models.FloatField()
    is_statistical = models.BooleanField()
    land_area = models.FloatField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=["state", "key"]),
            models.Index(fields=["state", "whole_key"])
        ]