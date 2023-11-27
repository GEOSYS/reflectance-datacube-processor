from enum import Enum
from pydantic import BaseModel


class Bands(Enum):
    """
    Available band values
    """
    RED = "red"
    GREEN = "green"
    BLUE = "blue"
    NIR='nir08'
    NIR9='nir09'
    SWIR1='swir16'
    SWIR2='swir22'
    REDEDGE1='rededge1'
    REDEDGE2='rededge2'
    REDEDGE3='rededge3'
    LST='lst'

class Collections(Enum):
    """
    Available sensor values
    """
    Sentinel_2 = "Sentinel-2 L2A"
    Landsat = "Landsat C2L2"
    Venus = "Venus L2A"
    ED_simulated = "EarthDaily Simulated L2A"

class CloudMask(Enum):
    """
    Available sensor values
    """
    native = 'native'
    acm = 'ag_cloud_mask'
class CloudStorageRepo(Enum):
    """
    Available Cloud Storage provider
    """
    AWS = "AWS_S3"
    AZURE = "AZURE_BLOB_STORAGE"

class Question(Enum):
    no = 'No'
    yes = 'Yes'