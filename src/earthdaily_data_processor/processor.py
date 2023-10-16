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
            Returns:
                xarray.Dataset
        """
        # Build a list with datasets of each indicator
        sensors_datasets = []
        pol = shapely.wkt.loads(polygon)
        dataframe_pol = gpd.GeoDataFrame([[1,pol]],columns=['id','geometry'])
        dataframe_pol.set_geometry('geometry',inplace=True)
        dataframe_pol.set_crs('epsg:4326',inplace=True)
        sensor_done = []
        
        if 'lst' in assets :
            lst=True
            assets.remove('lst')
        else:
            lst=False
            
        #re authenticate if needed
        self.check_client_auth()
        
        #datacube creation for each collections wanted
        for sens in collections:
            try:
                logging.info(f"EarthDailyData:generate_datacube_optic: Get dataset for {sens}")
                if sens =="sentinel-2-l2a":
                    sensors_datasets.append((self.get_sentinel(polygon = dataframe_pol,assets = assets,cloud_mask = cloud_mask,
                                            dates = [start_date, end_date], clear_percent= clear_percent))) 
                    
                elif  sens =="landsat-c2l2-sr":
                    sensors_datasets.append(self.get_landsat(polygon = dataframe_pol,assets = assets,cloud_mask = cloud_mask,
                                            dates = [start_date, end_date],base_dataset = sensors_datasets[0], clear_percent= clear_percent,lst_band=lst))
                
                    
                elif sens=='venus-l2a':
                    sensors_datasets.append(self.get_venus(polygon = dataframe_pol,assets = assets,cloud_mask = cloud_mask,
                                            dates = [start_date, end_date],base_dataset = sensors_datasets[0], clear_percent= clear_percent))
                
                elif sens=='earthdaily-simulated-cloudless-l2a-cog-edagro':
                    sensors_datasets.append(self.get_ed_simulated(polygon = dataframe_pol,assets = assets,
                                            dates = [start_date, end_date],base_dataset = sensors_datasets[0]))
                else:
                    print(f'Sensor {sens} not supported yet')  
                
                sensor_done.append(sens)                                                       
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
        band_adjusted = assets.copy()
        if 'rededge1' in assets:
            band_adjusted.remove('rededge1')
        if 'rededge2' in assets:
            band_adjusted.remove('rededge2')
        if 'rededge3' in assets:
            band_adjusted.remove('rededge3')
            
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
        
        else:
            data_cube_landsat_all = data_cube.copy()
        return(data_cube_landsat_all)  
    
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
        data_cube = self.__client_eds.datacube(
                        'earthdaily-simulated-cloudless-l2a-cog-edagro',
                        intersects = polygon,
                        datetime = dates,
                        assets = assets,
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
        venus_assets_reversed = dict(
            image_file_SRE_B3="blue",
            image_file_SRE_B4="green",
            image_file_SRE_B7="red",
            image_file_SRE_B8="rededge1",
            image_file_FRE_B9='rededge2',
            image_file_FRE_B10='rededge3',
            )
        
        
        lst_venus_assets = []
        for band in assets:
            try:
                lst_venus_assets.append(venus_assets[f'{band}'])
            except:
                pass
        dict_venus_assets = {i:venus_assets_reversed[f'{i}'] for i in lst_venus_assets}
        
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
            data_cube = data_cube.sel(time=data_cube.time[data_cube.clear_percent_ag_cloud_mask >= clear_percent])
        return(data_cube)
        
    def create_metacube(self,
                       *list_datacube: Dataset,
                        ):
        
        final_cube = earthdatastore.metacube(*list_datacube, concat_dim="time", by="time.date", how="mean")
        return(final_cube)
