from leapp.models import Model, fields
from leapp.topics import VendorTopic


class VendorSourceRepos(Model):
    """
    This model contains the data on all source repositories associated with a specific vendor.
    Its data is used to determine whether the vendor should be included into the upgrade process.
    """
    topic = VendorTopic
    vendor = fields.String()
    source_repoids = fields.List(fields.String())
