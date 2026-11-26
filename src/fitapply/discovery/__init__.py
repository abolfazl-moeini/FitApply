"""Job discovery module index and registry."""

from typing import Dict, List, Type
from fitapply.discovery.base import BaseDiscoverer, JobPosting
from fitapply.discovery.iran_boards import IranTalentDiscoverer, JobinjaDiscoverer, JobvisionDiscoverer
from fitapply.discovery.global_boards import GlobalBoardsDiscoverer

DISCOVERERS: Dict[str, Type[BaseDiscoverer]] = {
    "jobinja": JobinjaDiscoverer,
    "jobvision": JobvisionDiscoverer,
    "irantalent": IranTalentDiscoverer,
    "linkedin": lambda: GlobalBoardsDiscoverer(sites=["linkedin"]),
    "indeed": lambda: GlobalBoardsDiscoverer(sites=["indeed"]),
    "global": GlobalBoardsDiscoverer,
}


def get_discoverers_for_platforms(platforms: List[str]) -> List[BaseDiscoverer]:
    """Instantiate discoverers matching the requested platform names."""
    instances = []
    seen = set()

    for p in platforms:
        p_clean = p.lower().strip()
        if p_clean in DISCOVERERS and p_clean not in seen:
            seen.add(p_clean)
            factory = DISCOVERERS[p_clean]
            instances.append(factory() if callable(factory) else factory)

    return instances
