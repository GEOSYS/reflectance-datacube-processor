import logging
from typing import List

from dotenv import load_dotenv
from fastapi import FastAPI, Query, HTTPException
from fastapi.openapi.docs import get_swagger_ui_html
import time
from earthdaily_data_processor.processor import EarthDailyData
from earthdaily_data_processor.utils import dataset_to_zarr_format_indep_sensor,dataset_to_zarr_format_sensor
from api.constants import CloudStorageRepo, Bands, Collections, CloudMask, Question
from cloud_storage import cloud_storage_aws, cloud_storage_azure
from fastapi.staticfiles import StaticFiles
from geosyspy.geosys import Region, Env
from pydantic import BaseModel
import datetime as dt
from pydantic import BaseModel, Field
import numpy as np


app = FastAPI(
    docs_url=None,
    title="EarthDaily Data Processor",
    description="Get datasets from EarthData Store and package them as datacubes."
)
app.mount("/static", StaticFiles(directory="./api/files"), name="static")


@app.get("/docs", include_in_schema=False)
async def swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="EarthDaily Data Processor",
        swagger_favicon_url="/static/favicon.svg"
    )


logger = logging.getLogger()
logger.setLevel(logging.WARNING)

load_dotenv()


class Item(BaseModel):
    geometry: str = Field(...,
                        example="POLYGON ((1.26 43.427, 1.263 43.428, 1.263 43.426, 1.26 43.426, 1.26 43.427))")
    startDate: dt.date = Field(..., example="2019-05-01")
    endDate: dt.date = Field(..., example="2019-05-31")
    EntityID: str=Field(...,example='entity_1') 


@app.post("/earthdaily-data-processor", tags=["Datacube Computation"])
async def create_analytics_datacube(item: Item, CloudStorage: CloudStorageRepo = Query(...),
                                    Collections: List[Collections] = Query(...),
                                    Assets: List[Bands] = Query(...),
                                    CloudMask: CloudMask = Query(...),
                                    CreateMetacube:Question=Query(...),
                                    CloudClearPercent: int = Query(default=0,allow_inf_nan=False,examples=[0,10,50,80,90,100])):
    start_time = time.time()
    client = EarthDailyData()
    start_date = dt.datetime(item.startDate.year, item.startDate.month, item.startDate.day)
    end_date = dt.datetime(item.endDate.year, item.endDate.month, item.endDate.day)

    # generate analytics datacube
    datacubes, collections_done = client.generate_datacube_optic(polygon=item.geometry, start_date=start_date, end_date=end_date,
                                                            collections=[collection.value for collection in Collections],
                                                            assets=[asset.value for asset in Assets],
                                                            cloud_mask=CloudMask.value,
                                                            clear_percent=CloudClearPercent)
    
    links=[]
    if len(datacubes)>0:
        if CreateMetacube.value == 'Yes':
            cube = client.create_metacube(*datacubes)
            zarr_path = dataset_to_zarr_format_indep_sensor(cube,item.EntityID,item.startDate,item.endDate)
            try:
                # upload result on chosen CloudStorage provider (AWS or Azure)
                if CloudStorage == CloudStorageRepo.AWS and cloud_storage_aws.upload_folder_to_aws_s3(zarr_path):
                    logger.info("EarthDaily DataCube uploaded to AWS S3")
                    links.append(cloud_storage_aws.get_s3_uri_path(zarr_path))
                elif CloudStorage == CloudStorageRepo.AZURE and cloud_storage_azure.upload_directory_to_azure_blob_storage(
                        zarr_path):
                    logger.info("EarthDaily DataCube uploaded to Azure Blob Storage")
                    links.append(cloud_storage_azure.get_azure_blob_url_path(zarr_path))
            except Exception as exc:
                logging.error(f"Error while uploading folder to {CloudStorage.value}: {exc}")
                raise HTTPException(status_code=500, detail=f"Error while uploading folder to {CloudStorage.value} : {exc}")
        else: 
            for datacube in range(len(datacubes)):
                # convert the generated datacube in zarr file
                zarr_path = dataset_to_zarr_format_sensor(datacubes[datacube],item.EntityID,item.startDate,item.endDate,collections_done[datacube])
                try:
                        # upload CloudStorage on chosen CloudStorage provider (AWS or Azure)
                    if CloudStorage == CloudStorageRepo.AWS and cloud_storage_aws.upload_folder_to_aws_s3(zarr_path):
                        logger.info("EarthDaily DataCube uploaded to AWS S3")
                        links.append(cloud_storage_aws.get_s3_uri_path(zarr_path))
                    elif CloudStorage == CloudStorageRepo.AZURE and cloud_storage_azure.upload_directory_to_azure_blob_storage(
                            zarr_path):
                        logger.info("EarthDaily DataCube uploaded to Azure Blob Storage")
                        links.append(cloud_storage_azure.get_azure_blob_url_path(zarr_path))
                except Exception as exc:
                    logging.error(f"Error while uploading folder to {CloudStorage.value}: {exc}")
                    raise HTTPException(status_code=500, detail=f"Error while uploading folder to {CloudStorage.value} : {exc}")
                    
        return {"Storage_links": links,
                "Execution time":(f"--- {int(np.round((time.time() - start_time)/60))} minutes {int(np.round(np.round((time.time() - start_time))%60))} seconds ---" )}
        
    else:
        return('No item were found.')
    
            
