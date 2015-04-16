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

logger = logging.getLogger(__name__)


class WeatherScraper(object):
    def __init__(self,wwo_apikey):
        logging.basicConfig()
        logger.debug("Initializing Weather Scraper")
        self.cache = []
        #self.bbc_cache = self._scrapeBBCLocations()
        self.bbc_cache = self._scrapeAllBBC()
        self.wwo_apikey = wwo_apikey
        self.wwo_marineurl = "http://api.worldweatheronline.com/free/v2/marine.ashx?key={key}&tide=yes&format=json&q={lat},{lon}"
        self.wwo_searchurl = "http://api.worldweatheronline.com/free/v2/search.ashx?key={key}&q={lat},{lon}&format=json"

    def _scrapeAllBBC(self):
        r = requests.get("http://www.bbc.co.uk/weather/coast_and_sea/tide_tables")
        locations = {}
        if r.status_code != 200:
            logger.error("Could not retreive tidal data from the BBC")
            return

        root = html.document_fromstring(r.text)
        locs = root.xpath("//a[@data-location-name]")
        for loc in locs:
            locale = loc.get("data-location-name")
            href = loc.get("data-ajax-href")
            locations[locale] = href
            #Patches for the places in wales that might have the wrong name stored!
            if locale == "Aberdyfi":
                locations["Aberdovey"] = href

        logger.debug("Recorded HREF for {} different locations".format(len(locations)))
        if "Aberystwyth" in locations:
            logger.info("Aberystwyth (a sign of awesomeness) was found in the dataset")

        return locations

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

    def _findClosestFromSitelist(self,latX,lonX,wwoLocations):
        if len(wwoLocations) == 1:
            return wwoLocations.keys()[0]

        lat = self._makePositive(latX)
        lon = self._makePositive(lonX)

        best = {'wwoAreaName':'None','diffSum':179}
        for wwoAreaName in wwoLocations.keys():
            lat_in = self._makePositive(float(wwoLocations[wwoAreaName]['lat']))
            lon_in = self._makePositive(float(wwoLocations[wwoAreaName]['lon']))

            diffLat = self._makePositive(lat - lat_in)
            diffLon = self._makePositive(lon - lon_in)
            diffSum = diffLat+diffLon

            if diffSum < best['diffSum']:
                best['wwoAreaName'] = wwoAreaName

        return best['wwoAreaName']

    def getConditions(self,lat,lon):
        logger.debug("Attempting to get conditions at {},{}".format(lat,lon))
        """
        Get approximate location from WWO
        If that location includes tidal information, return it all pretty
        If not, it might be a position in the UK, grok the BBC tides page using the location from WWO for a town/port name
        """
        """
            "lowTideHeight"=>1.3,
            "lowTideHour"=>11,
            "lowTideMinute"=>30,
            "lowTideTimePretty"=>"11:30",
            "lowTideHeightPretty"=>"1.3m",
            "highTideHeight"=>3.9,
            "highTideHour"=>17,
            "highTideMinute"=>41,
            "highTideTimePretty"=>"17:41",
            "highTideHeightPretty"=>"3.9m",
        """

        #Get general tidal weather at that Lat and Lon
        waveUrl = self.wwo_marineurl.format(key=self.wwo_apikey,lat=lat,lon=lon)

        ret = requests.get(waveUrl)
        if ret.status_code != 200:
            logger.error("Unable to retrieve maritime weather conditions")
            raise Exception("Unable to locate")
        else:
            logger.debug("Retreived Maritime Conditions")

        data = ret.json()
        weather = data['data']['weather'][0]['hourly'][0]

        response = {}
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

        #Attempt to scrape the BBC website for tidal info - works only for UK
        if not self.locatedInUK(float(lat),float(lon)):
            logger.debug("Location not within the UK - cannot find tidal data")
            return response

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

        matchedWithBBC = {}
        for wwoAreaName in wwoLocations.keys():
            for bbckey in self.bbc_cache.keys():
                if wwoAreaName.lower() == bbckey.lower():
                    matchedWithBBC[bbckey] = wwoLocations[wwoAreaName]

        if not matchedWithBBC:
            logger.debug("Unable to match a location from:'{}' to those with tidal information from the BBC\n{}".format(sorted(wwoLocations),sorted(self.bbc_cache.keys())))
            return response

        closestLocationName = self._findClosestFromSitelist(lat, lon, matchedWithBBC)
        logger.debug("Closest location to original lat/lon appears to be {}".format(closestLocationName))

        tides = None
        try:
            logger.debug("BBC site matched with WWO location response: {}".format(closestLocationName))
            tides = self.scrapeBBC(location=closestLocationName)
        except:
            logger.debug("Unable to retreive tidal information for {}".format(closestLocationName))

        if tides:
            logger.debug("Tides \n{}".format(json.dumps(tides,sort_keys=True,indent=4,separators=(',',': '))))
            #response.update({'tides':tides})
            #API no longer returns the whole tide set

        dayofmonth = time.strftime("%d")
        hour = time.strftime("%H")
        response['dayofmonth']=int(dayofmonth)
        response["hour"]=int(hour)
        
        for tide in tides[:2]:
            if tide['type'] == 'High':
                response['nextHighTideTime']=tide['time']
                response['nextHighTideHeight']=tide['height']
            elif tide['type'] == 'Low':
                response['nextLowTideTime']=tide['time']
                response['nextLowTideHeight']=tide['height']
        
        return response

    def scrapeBBC(self,location):
        directurl = "http://www.bbc.co.uk{}".format(self.bbc_cache[location])
        logger.debug("Attempting to scrape BBC for {} using {}".format(location, directurl))

        page = requests.get(directurl)

        # Our data is within a table inside <div class="ui-tabs-panel open" id="tide-details0">
        soup = bs4.BeautifulSoup(page.text)
        table = soup.find("div", {"class" : "ui-tabs-panel open"} )
        if table == None:
            logger.error(page.text)

        tides = []
        for row in table.findAll("tr"):
            th = row.find('th')
            if 'High' in th.text or 'Low' in th.text:
                time = th.find_next_sibling()
                height = time.find_next_sibling()
                tides.append({'type': th.text, 'time':time.text,'height':height.text})
            else:
                continue

        return tides
