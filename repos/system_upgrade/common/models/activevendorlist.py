from leapp.models import Model, fields
from leapp.topics import VendorTopic


class ActiveVendorList(Model):
    topic = VendorTopic
    data = fields.List(fields.String())
