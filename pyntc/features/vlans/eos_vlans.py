from ..base_feature import BaseFeature

class EOSVlans(BaseFeature):
    def __init__(self, device):
        self.device = device

def instance(device):
    return EOSVlans(device)