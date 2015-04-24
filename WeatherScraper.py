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

logger = logging.getLogger(__name__)


class WeatherScraper(object):
    def __init__(self,wwo_apikey):
        logging.basicConfig()
        logger.debug("Initializing Weather Scraper")
        self.cache = []
        #self.bbc_cache = self._scrapeBBCLocations()
        self.wwo_apikey = wwo_apikey
        self.wwo_marineurl = "http://api.worldweatheronline.com/free/v2/marine.ashx?key={key}&tide=yes&format=json&q={lat},{lon}"
        self.wwo_searchurl = "http://api.worldweatheronline.com/free/v2/search.ashx?key={key}&q={lat},{lon}&format=json"

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


    #We can't be sure which location is the best
    def scrapeTideForecast(self,locations,bestguess=None):
        #Lets try a one-shot with what we believe is the best location first - avoids hammering the API
        
        if bestguess:
            logger.debug("Attempting oneshot lookup against {}".format(bestguess))
            page = requests.post("http://www.tide-forecast.com/locations/catch",data={'query':bestguess})
            
        if page.status_code != 200:
            logger.debug("Oneshot failed, removing {} from locations".format(bestguess))
            locations.remove(bestguess)
            for location in locations:
                page = requests.post("http://www.tide-forecast.com/locations/catch",data={'query':location})
                if page.status_code == 200:
                    logger.debug("Lookup for {} succeeded!".format(location))
                    break
                else:
                    logger.debug("Lookup for {} failed".format(location))
            
        if page.status_code != 200:
            #Loop completed without finding anything valuable
            raise Exception("Couldn't find a viable location")
        
        root = html.document_fromstring(page.text)
        scripts = root.xpath("//script[@src]")
        locname = None
        for script in scripts:
            if location.lower() in script.get('src').lower():
                for part in script.get('src').split("/"):
                    if location.lower() in part.lower():
                        locname = part.split(".")[0]
                
        if not locname:
            logger.error("Could not find location {}".format(location))
            return
        
        data = []
        page = requests.get("http://www.tide-forecast.com/tides/{}.js".format(locname))
        if page.status_code != 200:
            logger.error(page.text)
            logger.error('locname = {}'.format(locname))
        for line in page.text.split():
            cleanline = line.strip('[').strip(',').strip(']')
            elements = cleanline.split(",")
            if len(elements) == 4:
                ld = {'x':int(elements[0]),
                      'y':int(elements[1]),
                      'epoch':int(elements[2]),
                      'height':float(elements[3]),
                }
                data.append(ld)
        
        return data

    def getConditions(self,lat,lon):
        logger.debug("Attempting to get conditions at {},{}".format(lat,lon))
        """
        Get approximate location from WWO
        If that location includes tidal information, return it all pretty
        If not, it might be a position in the UK, grok the BBC tides page using the location from WWO for a town/port name
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

        tides = None
        data = None
        
        try:
            logger.debug("Attempting to find tidal data for any of {}".format(wwoLocations))
            data = self.scrapeTideForecast(wwoLocations.keys(),bestguess=closestLocationName)
        except Exception as e:
            import traceback
            traceback.print_exc()
    
        if data != None:
            today = datetime.date.today()
            yesterday = today - datetime.timedelta(1)
            tomorrow = today + datetime.timedelta(1)
            
            todayDate = today.strftime("%d-%m-%Y")
            yesterdayDate = yesterday.strftime("%d-%m-%Y")
            tomorrowDate = tomorrow.strftime("%d-%m-%Y")
            
            days = self.orderByDays(data)
            logger.debug("Tides for days: {}".format(days.keys()))
            
            tidesToday = self.getTides(days[todayDate])
            tidesYesterday = self.getTides(days[yesterdayDate])
            tidesTomorrow = self.getTides(days[tomorrowDate])
            response['tidesToday'] = tidesToday
            response['tidesTomorrow'] = tidesTomorrow
            response['tidesYesterday'] = tidesYesterday            

        dayofmonth = time.strftime("%d")
        hour = time.strftime("%H")
        response['dayofmonth']=int(dayofmonth)
        response["lastReport"]=time.strftime("%H:%M")
        
        return response
    
    def orderByDays(self,data):
    #Convert some times
        days = {}
        for entry in data:
            entry['timestr'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(entry['epoch']))
            ydelta = time.localtime(entry['epoch'] + entry['y'])
            entry['date'] = time.strftime("%d-%m-%Y", ydelta)
            entry['time'] = time.strftime("%H:%M:%S", ydelta)
            
            if entry['date'] not in days:
                days[entry['date']] = []
                
            days[entry['date']].append(entry)
            
            #if entry['date'] == '17-04-2015':
            #   logger.info("{} - {:.1f}m".format(entry['time'],entry['height']))            
        
        return days

    #The dataset includes lots of tidal datapoints, this function finds the extremes i.e high and low water
    def getTides(self,dataset):
        tides = []     
        state = 'unknown'
        for i in range(1,len(dataset)):
            if state == 'unknown':
                if dataset[i]['height'] < dataset[i-1]['height']:
                    state = 'dropping'
                else:
                    state = 'rising'
                
            #Rather than looking for the lowest value we look for when the tide turns
            #Possibly need to introduce some countback in case data sets are the same ie slack water
            if state == 'dropping':
                if dataset[i]['height'] > dataset[i-1]['height']:
                    #logger.debug("{} {:.1f}m - Low tide".format(dataset[i-1]['time'],dataset[i-1]['height']))
                    heightPretty = "{:.1f}m".format(dataset[i-1]['height'])
                    thetime = ":".join(dataset[i-1]['time'].split(":")[0:2])
                    tides.append({'time':thetime, 'height':dataset[i-1]['height'], 'type':'Low', 'heightPretty':heightPretty})
                    state = 'rising'
                    
            if state == 'rising':
                if dataset[i]['height'] < dataset[i-1]['height']:
                    #logger.debug("{} {:.1f}m - High tide".format(dataset[i-1]['time'],dataset[i-1]['height']))
                    heightPretty = "{:.1f}m".format(dataset[i-1]['height'])
                    thetime = ":".join(dataset[i-1]['time'].split(":")[0:2])
                    tides.append({'time':thetime, 'height':dataset[i-1]['height'], 'type':'High', 'heightPretty':heightPretty})
                    state = 'dropping'
                
            if dataset[i]['height'] == dataset[i-1]['height']:
                logger.info("Two adjacent tides with height {}m".format(dataset[i]['height']))
                    
        return tides
        
