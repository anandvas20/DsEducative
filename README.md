String dataJson = """
{
  "sku": "SKU12345",
  "name": "Bluetooth Speaker",
  "active": true,
  "stock": 150,
  "tags": ["audio", "portable", "bluetooth"],
  "specs": {
    "color": "black",
    "batteryLife": "10h"
  },
  "rating": null
}
""";

String responseJson = """
{
  "PRICE": {
    "value": 29.99,
    "currency": "USD",
    "discount": {
      "amount": 5,
      "percentage": 14.3
    }
  },
  "IMAGE_URL_MAP": {
    "main": "https://example.com/images/main.jpg",
    "thumbnail": "https://example.com/images/thumb.jpg",
    "gallery": [
      "https://example.com/images/1.jpg",
      "https://example.com/images/2.jpg"
    ]
  },
  "description": "High-quality portable Bluetooth speaker.",
  "available": true,
  "releaseDate": "2024-12-01",
  "dimensions": {
    "width": 10.5,
    "height": 4.0,
    "depth": 3.0
  },
  "extraAttributes": null
}
""";