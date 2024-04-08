from leapp.models import Model, fields
from leapp.topics import VendorTopic


class VendorSignatures(Model):
    topic = VendorTopic
    vendor = fields.String()
    sigs = fields.List(fields.String())
