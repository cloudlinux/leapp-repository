from leapp.actors import Actor
# from leapp.libraries.common.repomaputils import scan_vendor_repomaps, VENDOR_REPOMAP_DIR
from leapp.libraries.actor.vendorrepositoriesmapping import scan_vendor_repomaps
from leapp.models import VendorSourceRepos, RepositoriesMapping
from leapp.tags import FactsPhaseTag, IPUWorkflowTag


class VendorRepositoriesMapping(Actor):
    """
    Scan the vendor repository mapping files and provide the data to other actors.
    """

    name = "vendor_repositories_mapping"
    consumes = ()
    produces = (RepositoriesMapping, VendorSourceRepos,)
    tags = (IPUWorkflowTag, FactsPhaseTag.Before)

    def process(self):
        scan_vendor_repomaps()
