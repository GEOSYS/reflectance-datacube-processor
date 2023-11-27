import logging
from typing import List

from dotenv import load_dotenv
from fastapi import FastAPI, Query, HTTPException
from fastapi.openapi.docs import get_swagger_ui_html
import time
from earthdaily_data_processor.processor import EarthDailyData
from earthdaily_data_processor.utils import dataset_to_zarr_format_indep_sensor,dataset_to_zarr_format_sensor, upload_cube
from api.constants import CloudStorageRepo, Bands, Collections, CloudMask, Question
from cloud_storage import cloud_storage_aws, cloud_storage_azure
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import datetime as dt
from pydantic import BaseModel, Field
import numpy as np
import psutil
from os import environ


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
async def create_analytics_datacube(item: Item, cloud_storage: CloudStorageRepo = Query(alias="Cloud Storage"),
                                    collections: List[Collections] = Query(alias="Collections"),
                                    assets: List[Bands] = Query(alias="Assets"),
                                    cloud_mask: CloudMask = Query(alias="Cloud Mask"),
                                    create_metacube:Question=Query(alias="Create Metacube"),
                                    clear_coverage: int = Query(default=0,alias="Clear Coverage (%)",allow_inf_nan=False,examples=[0,10,50,80,90,100])):
    
    # initialization 
    start_time = time.time()
    links=[]
    client = EarthDailyData()
    start_date = dt.datetime(item.startDate.year, item.startDate.month, item.startDate.day)
    end_date = dt.datetime(item.endDate.year, item.endDate.month, item.endDate.day)

    # generate analytics datacube
    datacubes, collections_done = client.generate_datacube_optic(polygon=item.geometry, start_date=start_date, end_date=end_date,
                                                            collections=[collection.value for collection in collections],
                                                            assets=[asset.value for asset in assets],
                                                            cloud_mask=cloud_mask.value,
                                                            clear_percent=clear_coverage)
    # bandwidth use retrieval
    bandwidth_generation = psutil.net_io_counters().bytes_sent + psutil.net_io_counters().bytes_recv
    
    if len(datacubes)>0:
        if create_metacube.value == 'Yes':
            cube = client.create_metacube(*datacubes)
            zarr_path = dataset_to_zarr_format_indep_sensor(cube,item.EntityID,item.startDate,item.endDate)
            try:
                links.append(upload_cube(zarr_path,cloud_storage))
            except Exception as exc:
                logging.error(f"Error while uploading folder to {cloud_storage.value}: {exc}")
                raise HTTPException(status_code=500, detail=f"Error while uploading folder to {cloud_storage.value} : {exc}")
        else: 
            for i, datacube in enumerate(datacubes):
                # convert the generated datacube in zarr file
                zarr_path = dataset_to_zarr_format_sensor(datacube, item.EntityID, item.startDate, item.endDate, collections_done[i])
                try:
                    links.append(upload_cube(zarr_path,cloud_storage))
                except Exception as exc:
                    logging.error(f"Error while uploading folder to {cloud_storage.value}: {exc}")
                    raise HTTPException(status_code=500, detail=f"Error while uploading folder to {cloud_storage.value} : {exc}")
        # bandwidth use retrieval
        bandwidth_upload = psutil.net_io_counters().bytes_sent + psutil.net_io_counters().bytes_recv               
        
        if environ.get('bandwidth')=='True':
            return {"Storage_links": links,
                "Execution time":(f"--- {int(np.round((time.time() - start_time)/60))} minutes {int(np.round(np.round((time.time() - start_time))%60))} seconds ---" ),
                "Datacube generation network use":(f"--- {np.round((bandwidth_generation)/1024./1024./1024.*8,3)} Gb ---" ),
                "Datacube upload network use":(f"--- {np.round((bandwidth_upload-bandwidth_generation)/1024./1024./1024.*8,3)} Gb ---" )}
        else:
            return {"Storage_links": links,
                "Execution time":(f"--- {int(np.round((time.time() - start_time)/60))} minutes {int(np.round(np.round((time.time() - start_time))%60))} seconds ---" )}
        
        
    else:
        return('No item were found.')
    
            
