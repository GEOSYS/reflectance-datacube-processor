# -*- coding: utf-8 -*-
"""
Created on Sep 12

@author: lwh
"""
#%%
import logging
import os
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
from geosyspy import Geosys
from geosyspy.utils.constants import *

import geopandas as gpd

import xarray as xr
from xarray import DataArray, Dataset
from earthdaily import earthdatastore
import shapely
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

#%%
class EarthDailyData:

    def __init__(self):
        
        load_dotenv()
        self.__client_eds = earthdatastore.Auth()
        self.sensors = ["sentinel-2-l2a","landsat-c2l2",'venus-l2a','earthdaily-simulated-cloudless-l2a-cog-edagro']
    
    
    def check_client_auth(self,) :
        '''
        Function to check the EarthDataStore authentication. If needed, the function will re-authenticate.
        '''
        try:
            collections  = [i.id for i in list(self.__client_eds.get_all_collections())]
        except: 
            self.__init__()
        return(None)
    def generate_datacube_optic(self,
                                polygon,
                                start_date: str,
                                end_date: str,
                                collections: [str],
                                assets: [str],
                                cloud_mask: str,
                                clear_percent:int=80):
        """
            Get a xarray.Dataset with indicators values for each pixel and for each date of images found between start and end dates.

            Args:
                - polygon: WKT
                - start_date: beginning of the period
                - end_date: end of the period
                - collections : sensor to use : "sentinel-2-l2a",landsat-c2l2-sr, venus-l2a
                - assets : list of band to get, among : ["red", "green", "blue",  "nir08", "swir16", "swir22","lst]
                - cloud_mask : cloud mask to use : "native" or "ag_cloud_mask"
                - clear_percent : clear coverage percentage to select the image takes : int between 0 and 100.
            Returns:
                xarray.Dataset
        """
        # Initiate an empty list for the datasets of each collections selected
        sensors_datasets = []
        sensor_done = []
        
        #specific assets by collections management
        if 'lst' in assets : #thermal band from Landsat
            lst=True
            assets.remove('lst')
        else:
            lst=False
        
        if 'nir09' in assets: #band B08A from S2
            nir09=True
            assets.remove('nir09')
        else:
            nir09=False
            
        #re authenticate if needed
        self.check_client_auth()
        
        if "Sentinel-2 L2A" not in collections:
            base_dataset =  (self.get_sentinel(polygon = polygon,assets = assets,cloud_mask = 'native',
                                            dates = [start_date, end_date], clear_percent= clear_percent))
        
        #datacube creation for each collections wanted
        for sens in collections:
            try:
                logging.info(f"EarthDailyData:generate_datacube_optic: Get dataset for {sens}")
                if sens =="Sentinel-2 L2A":
                    if nir09==True:
                        assets.append('nir09')
                    datacube = (self.get_sentinel(polygon = polygon,assets = assets,cloud_mask = cloud_mask,
                                            dates = [start_date, end_date], clear_percent= clear_percent))
                    sensors_datasets.append(datacube.copy()) 
                    base_dataset = datacube.copy()
                    sensor_done.append(self.sensors[0])
                    
                elif  sens =="Landsat C2L2":
                    sensors_datasets.append(self.get_landsat(polygon = polygon,assets = assets,cloud_mask = cloud_mask,
                                            dates = [start_date, end_date],base_dataset = base_dataset, clear_percent= clear_percent,lst_band=lst))
                    sensor_done.append(self.sensors[1])
                    
                elif sens=="Venus L2A":
                    sensors_datasets.append(self.get_venus(polygon = polygon,assets = assets,cloud_mask = cloud_mask,
                                            dates = [start_date, end_date],base_dataset = base_dataset, clear_percent= clear_percent))
                    sensor_done.append(self.sensors[2])
                    
                elif sens=="EarthDaily Simulated L2A":
                    sensors_datasets.append(self.get_ed_simulated(polygon = polygon,assets = assets,
                                            dates = [start_date, end_date],base_dataset = base_dataset))
                    sensor_done.append(self.sensors[3])
                    
                else:
                    print(f'Sensor {sens} not supported yet')  
                    
            except Exception as exc:
                logging.error(f"Error while generating dataset for {sens} indicator: {str(exc)}")
        
        return sensors_datasets, sensor_done
    
    def get_sentinel(self, 
                polygon: gpd.GeoDataFrame,
                assets: [str],
                cloud_mask: str,
                dates: [str],
                clear_percent:int
                ) ->Dataset:
        '''
        Function to retrieve a landsat datacube.
        Parameters:
            - polygon : GeoDataFrame, polygon to extract the data for.
            - assets : [str], assets to extract.
            - cloud_mask : str, cloud mask to use, either 'native' or 'ag_cloud_mask'.
            - dates : [str], dates to extract the data for.
            - clear_percent: int, cloud free percentage wanted.
            
        Returns:
        xarray.Dataset 
        '''
        data_cube = self.__client_eds.datacube(
                    "sentinel-2-l2a",
                    intersects=polygon,
                    datetime=dates,
                    assets=assets,
                    rescale=True,
                    mask_with=cloud_mask,  
                    mask_statistics=True,
                    prefer_alternate="download"
                    ) 

        if cloud_mask == 'native':
            data_cube = data_cube.sel(time=data_cube.time[data_cube.clear_percent_scl >= clear_percent])
        elif cloud_mask =='ag_cloud_mask':
            data_cube = data_cube.sel(time=data_cube.time[data_cube.clear_percent_ag_cloud_mask >= clear_percent])
        return(data_cube)
    
    def get_landsat(self, 
                    polygon: gpd.GeoDataFrame,
                    assets: [str],
                    cloud_mask: str,
                    dates: [str],
                    base_dataset: Dataset,
                    clear_percent:int,
                    lst_band: bool
                    ) ->Dataset:
        '''
        Function to retrieve a landsat datacube.
        Parameters:
            - polygon : GeoDataFrame, polygon to extract the data for.
            - assets : [str], assets to extract.
            - cloud_mask : str, cloud mask to use, either 'native' or 'ag_cloud_mask'.
            - dates : [str], dates to extract the data for.
            - base_dataset: xarray.Dataset, first dataset computed to scale the datacube with.
            - clear_percent: int, cloud free percentage wanted.
            
        Returns:
        xarray.Dataset 
        '''
        #deal with rededge bands for landsat
        band_adjusted = list(filter(lambda asset: asset not in ["rededge1", "rededge2", "rededge3"], assets))

        #get datacube
        data_cube = self.__client_eds.datacube(
                    "landsat-c2l2-sr",
                    intersects=polygon,
                    datetime=dates,
                    assets=band_adjusted,
                    mask_with=cloud_mask,  
                    mask_statistics=True,
                    resolution=base_dataset.rio.resolution()[0],
                    epsg=base_dataset.rio.crs.to_epsg()
                ) 
        if cloud_mask == 'native':
            data_cube = data_cube.sel(time=data_cube.time[data_cube.clear_percent_qa_pixel >= clear_percent])
        elif cloud_mask =='ag_cloud_mask':
            data_cube = data_cube.sel(time=data_cube.time[data_cube.clear_percent_ag_cloud_mask >= clear_percent])
        if lst_band :
            
            data_cube_lst = self.__client_eds.datacube(
                            'landsat-c2l2-st',
                            intersects=polygon,
                            datetime=dates,
                            assets=['lwir11'],
                            mask_with=cloud_mask,  
                            mask_statistics=True,
                            search_kwargs=dict(query={"platform": {"in_": ["LANDSAT_8", "LANDSAT_9"]}}),
                            resolution=base_dataset.rio.resolution()[0],
                            epsg=base_dataset.rio.crs.to_epsg()
                        ) 
            if cloud_mask == 'native':
                data_cube_lst = data_cube_lst.sel(time=data_cube_lst.time[data_cube_lst.clear_percent_qa_pixel >= clear_percent])
            elif cloud_mask =='ag_cloud_mask':
                data_cube_lst = data_cube_lst.sel(time=data_cube_lst.time[data_cube_lst.clear_percent_ag_cloud_mask >= clear_percent])
            data_cube_landsat_all = xr.merge([data_cube,data_cube_lst],compat="no_conflicts")
            return data_cube_landsat_all
        else:
            return data_cube  
    
    def get_ed_simulated(self, 
                polygon: gpd.GeoDataFrame,
                assets: [str],
                dates: [str],
                base_dataset: Dataset,
                ) ->Dataset:
        '''
        Function to retrieve a cloudless EarthDaily simulated datacube.
        Parameters:
            - polygon : GeoDataFrame, polygon to extract the data for.
            - assets : [str], assets to extract.
            - dates : [str], dates to extract the data for.
            - base_dataset: xarray.Dataset, first dataset computed to scale the datacube with.
            
        Returns:
        xarray.Dataset 
        '''
        
        if 'swir22' in assets:
            assets.remove('swir22')
        
        simulated_assets = dict(
            blue='blue',
            green="green",
            red="red",
            rededge1= "image_file_RE1",
            rededge2= "image_file_RE2",
            rededge3= "image_file_RE3",
            nir08='image_file_NIR',
            swir16='swir16'
        )
        dict_simulated_assets = { simulated_assets[band]: band for band in assets}
        data_cube = self.__client_eds.datacube(
                        'earthdaily-simulated-cloudless-l2a-cog-edagro',
                        intersects = polygon,
                        datetime = dates,
                        assets = dict_simulated_assets,
                        resolution = base_dataset.rio.resolution()[0],
                        epsg = base_dataset.rio.crs.to_epsg(),
                        prefer_alternate="download"
                    ) 

        return(data_cube)
        
        
        
    def get_venus(self, 
                polygon: gpd.GeoDataFrame,
                assets: [str],
                cloud_mask: str,
                dates: [str],
                base_dataset: Dataset,
                clear_percent:int
                ) ->Dataset:
        '''
        Function to retrieve a Venus datacube.
        Parameters:
            - polygon : GeoDataFrame, polygon to extract the data for.
            - assets : [str], assets to extract.
            - cloud_mask : str, cloud mask to use, either 'native' or 'ag_cloud_mask'.
            - dates : [str], dates to extract the data for.
            - base_dataset: xarray.Dataset, first dataset computed to scale the datacube with.
            - clear_percent: int, cloud free percentage wanted.
            
        Returns:
        xarray.Dataset 
        '''
        venus_assets = dict(
            blue='image_file_SRE_B3',
            green="image_file_SRE_B4",
            red="image_file_SRE_B7",
            rededge1='image_file_FRE_B8',
            rededge2='image_file_FRE_B9',
            rededge3='image_file_FRE_B10'
        )

        dict_venus_assets = { venus_assets[band]: band for band in assets }
        data_cube = self.__client_eds.datacube(
                        'venus-l2a',
                        intersects = polygon,
                        datetime = dates,
                        assets = dict_venus_assets,
                        mask_with = cloud_mask,  
                        mask_statistics = True,
                        resolution = base_dataset.rio.resolution()[0],
                        epsg = base_dataset.rio.crs.to_epsg(),
                        prefer_alternate="download"
                    ) 
        if cloud_mask == 'native':
            data_cube = data_cube.sel(time=data_cube.time[data_cube.clear_percent_detailed_cloud_mask >= clear_percent])
        elif cloud_mask =='ag_cloud_mask':
            #no cloud mask available for venus so it will select the native one
            data_cube = data_cube.sel(time=data_cube.time[data_cube.clear_percent_detailed_cloud_mask >= clear_percent])
        return(data_cube)
        
    def create_metacube(self,
                       *list_datacube: Dataset,
                        ):
        
        final_cube = earthdatastore.metacube(*list_datacube, concat_dim="time", by="time.date", how="mean")
        return(final_cube)
