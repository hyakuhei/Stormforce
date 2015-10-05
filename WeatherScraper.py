'''
Created on 25 Mar 2015

@author: robert
'''

import bs4
import lxml.html as html
import requests

import json
import logging
import time
import datetime
import traceback


from TideForecastScraper import TideScraper

logger = logging.getLogger(__name__)


class WeatherScraper(object):
    def __init__(self,wwo_apikey):
        logging.basicConfig()
        logger.debug("Initializing Weather Scraper")
        self.cache = []
        #self.bbc_cache = self._scrapeBBCLocations()
        self.wwo_apikey = wwo_apikey
        self.wwo_marineurl = "http://api.worldweatheronline.com/free/v2/marine.ashx?key={key}&tide=yes&format=json&q={lat},{lon}"
        self.genonames_nearbyurl = "http://api.geonames.org/findNearbyPlaceNameJSON?lat={lat}&lng={lon}&username=stormforce"
        self.wwo_searchurl = "http://api.worldweatheronline.com/free/v2/search.ashx?key={key}&q={lat},{lon}&format=json"
        self.ts = TideScraper()

    def milesToKnots(self,miles):
        return float(miles) * 0.868976

    def locatedInUK(self,lat,lon):
        if lat > 50 and lat <60 and lon < 2 and lon > -10:
            logger.debug("Location {},{} is within the UK".format(lat,lon))
            return True
        else:
            return False
            logger.debug("Location {},{} is not located in the UK".format(lat,lon))

    def milesToBeaufort(self,mph):
        if mph < 1:
            return 0
        elif mph >= 1 and mph <= 3:
            return 1
        elif mph >= 4 and mph <= 7:
            return 2
        elif mph >= 8 and mph <= 12:
            return 3
        elif mph >= 13 and mph <= 18:
            return 4
        elif mph >= 19 and mph <= 24:
            return 5
        elif mph >= 25 and mph <= 31:
            return 6
        elif mph >= 32 and mph <= 38:
            return 7
        elif mph >= 39 and mph <= 46:
            return 8
        elif mph >= 47 and mph <= 54:
            return 9
        elif mph >= 55 and mph <= 63:
            return 10
        elif mph >= 64 and mph <= 72:
            return 11
        elif mph > 73:
            return 12

    def _makePositive(self,x):
        x = float(x)
        if x > 0:
            return x
        else:
            return x * -1

    def _findClosestFromSitelist(self,latX,lonX,locations):
        if len(locations) == 1:
            return locations.keys()[0]

        lat = self._makePositive(latX)
        lon = self._makePositive(lonX)

        best = {'name':'None','diffSum':179}
        for name in locations.keys():
            lat_in = self._makePositive(float(locations[name]['lat']))
            lon_in = self._makePositive(float(locations[name]['lon']))

            diffLat = self._makePositive(lat - lat_in)
            diffLon = self._makePositive(lon - lon_in)
            diffSum = diffLat+diffLon

            logger.debug("Location {} has a diff score of {}".format(name,diffSum))

            if diffSum < best['diffSum']:
                best['name'] = name
                best['diffSum'] = diffSum

        return best['name']

    def geonameLookup(self,lat,lon):
        r = requests.get(self.genonames_nearbyurl.format(lat=lat,lon=lon))
        if r.status_code == 200:
            data = json.loads(r.text)
            loc = data['geonames'][0]['name']
            return loc
        else:
            return None

    def wwoLocationLookup(self,lat,lon):
        #WWO has an interesting feature where you can give it a lat,lon and get some nearby locations
        locUrl = self.wwo_searchurl.format(key=self.wwo_apikey,lat=lat,lon=lon)

        ret = requests.get(locUrl)
        if ret.status_code != 200:
            raise Exception("Unable to reach api")

        locData = ret.json()
        wwoLocations = {}
        for loc in locData['search_api']['result']:
                name = loc['areaName'][0]['value']
                wwoLocations[name] = {
                              'lat':loc['latitude'],
                              'lon':loc['longitude'],
                              }

        logger.debug("WWO possible locations for {},{}\n{}".format(lat,lon,wwoLocations.keys()))

        closestLocationName = self._findClosestFromSitelist(lat, lon, wwoLocations)
        logger.debug("Closest location to original lat/lon appears to be {}".format(closestLocationName))
        return closestLocationName, wwoLocations

    def getConditions(self,lat,lon):
        """
        Get approximate location from WWO
        If that location includes tidal information, return it all pretty
        If not, it might be a position in the UK, grok the BBC tides page using the location from WWO for a town/port name
        """

        #Get general tidal weather at that Lat and Lon
        logger.debug("Attempting to get conditions at {},{}".format(lat,lon))
        waveUrl = self.wwo_marineurl.format(key=self.wwo_apikey,lat=lat,lon=lon)

        ret = requests.get(waveUrl)
        if ret.status_code != 200:
            logger.error("Unable to retrieve maritime weather conditions")
            raise Exception("Unable to locate")
        else:
            logger.debug("Retreived Maritime Conditions")

        
        response = {"hasWeather":False}
        data = ret.json()
        if "weather" not in data["data"]:
            logger.debug("WWO Maritime Weather Lookup Failed");
        else:
            try:
                weather = data['data']['weather'][0]['hourly'][0]
                response['windDirection16pt']=weather['winddir16Point']
                response['windDirection']=weather['winddirDegree']
                response['windSpeedKnots']=self.milesToKnots(weather['windspeedMiles'])
                response['windBeaufort']=self.milesToBeaufort(weather['windspeedMiles'])
                response['swellHeight']=weather['swellHeight_m']
                response['waveHeight']=weather['sigHeight_m']
                #response['swellDir16pt']=weather['swellDir16Point']
                response['swellDir']=weather['swellDir']
                response['swellPeriod']=weather['swellPeriod_secs']
                response['waterTemp']=weather['waterTemp_C']
                
                response['hasWeather']=False
            except Exception as e:
                logger.debug("WWO Maritime Weather is not formatted as expected")
                logger.debug(ret.json())
                
        #First off, we try to get the nearest location from GeoNames because their API has lots of capacity
        #If that doesn't work we'll try to fetch it from WWO

        tides = None
        data = None
        
        # Get a lookup from Geonames
        # Attempt to scrape just that from tide forecast
        # If that fails, get a bunch of places from WWO
        # Scrape tide forecast for each of them

        closestLocationName = self.geonameLookup(lat=lat,lon=lon)
        alternates = [closestLocationName]
        if closestLocationName != None:
            logger.debug("Geonames lookup returned {}".format(closestLocationName))
            try:
                logger.debug("Attempting to find tidal data for any of {}".format(alternates))
                data, establishedLocation = self.ts.scrapeTideForecast(alternates,bestguess=closestLocationName)
            except Exception as e:
                logger.error("WWO Lookup for {} failed".format(closestLocationName))
                logger.error(e)
        
        #if geonames couldn't find data _or_ the tide lookup failed        
        if closestLocationName == None or data == None:
            logger.debug("Falling back to WWO lookup")
            closestLocationName, wwodata = self.wwoLocationLookup(lat=lat,lon=lon)
            alternates = wwodata.keys()
            try:
                logger.debug("Attempting to find tidal data for any of {}".format(alternates))
                data, establishedLocation = self.ts.scrapeTideForecast(alternates,bestguess=closestLocationName)
            except Exception as e:
                logger.error(e)
        
        if data == None:
            errordata = {}
            if closestLocationName != None:
                errordata['error'] = "No Tide Data"
                errordata['location'] = closestLocationName
            else:
                errordat['error'] = "No Location Match"
            

        response['location'] = establishedLocation

        if data != None:
            today = datetime.date.today()
            yesterday = today - datetime.timedelta(1)
            tomorrow = today + datetime.timedelta(1)

            todayDate = today.strftime("%d-%m-%Y")
            yesterdayDate = yesterday.strftime("%d-%m-%Y")
            tomorrowDate = tomorrow.strftime("%d-%m-%Y")

            tidesToday = self.ts.getTides(data, todayDate)
            tidesYesterday = self.ts.getTides(data, yesterdayDate)
            tidesTomorrow = self.ts.getTides(data, tomorrowDate)

            logger.debug("Today's Tides: {}".format(tidesToday))

            response['tidesToday'] = tidesToday
            response['todayDate'] = todayDate
            response['yesterdayDate'] = yesterdayDate
            response['tomorrowDate'] = tomorrowDate
            response['tidesTomorrow'] = tidesTomorrow
            response['tidesYesterday'] = tidesYesterday

        dayofmonth = time.strftime("%d")
        hour = time.strftime("%H")
        response['dayofmonth']=int(dayofmonth)
        response["lastReport"]=time.strftime("%H:%M")

        return response
