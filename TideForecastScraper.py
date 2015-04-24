'''
Created on 16 Apr 2015

@author: robert
'''
import lxml.html as html
import requests
import logging
import time

logger = logging.getLogger(__name__)

class TideScraper():
    #We can't be sure which location is the best
    def scrapeTideForecast(self,locations,bestguess=None):
        #Lets try a one-shot with what we believe is the best location first - avoids hammering the API
        
        establishedLocation = None
        
        if bestguess:
            logger.debug("Attempting oneshot lookup against {}".format(bestguess))
            page = requests.post("http://www.tide-forecast.com/locations/catch",data={'query':bestguess})
            if page.status_code == 200:
                establishedLocation = bestguess
            
        if page.status_code != 200:
            logger.debug("Oneshot failed, removing {} from locations".format(bestguess))
            locations.remove(bestguess)
            for location in locations:
                page = requests.post("http://www.tide-forecast.com/locations/catch",data={'query':location})
                if page.status_code == 200:
                    logger.debug("Lookup for {} succeeded!".format(location))
                    establishedLocation = location
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
            if establishedLocation.lower() in script.get('src').lower():
                for part in script.get('src').split("/"):
                    if establishedLocation.lower() in part.lower():
                        locname = part.split(".")[0]
                
        if not locname:
            logger.error("Could not find location {}".format(establishedLocation))
            return
        
        data = []
        logger.debug("Fetching javascript data for {}".format(locname))
        page = requests.get("http://www.tide-forecast.com/tides/{}.js".format(locname))
        if page.status_code != 200:
            logger.error(page.text)
            logger.error('locname = {}'.format(locname))
        for line in page.text.split():
            cleanline = line.strip('[').strip(',').strip(']')
            elements = cleanline.split(",")
            if len(elements) == 4:
                ydelta = time.localtime(int(elements[2])+int(elements[1]))
                ld = {'x' : int(elements[0]),
                      'y' : int(elements[1]),
                      'epoch' : int(elements[2]),
                      'height' : float(elements[3]),
                      'date' : time.strftime("%d-%m-%Y", ydelta),
                      'time' : time.strftime("%H:%M", ydelta),
                }
                data.append(ld)
        
        return data,establishedLocation
        
    def getTidesForDate(self,dataset,datestr):
        day = []
        
        for d in dataset:
            if d['date'] == datestr:
                day.append(d)
        
        return day


    def getTides(self,wholedataset,datestr):
        dataset = self.getTidesForDate(wholedataset,datestr)
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
                    tides.append({'time':dataset[i-1]['time'], 'height':dataset[i-1]['height'], 'type':'Low tide', 'heightPretty':heightPretty})
                    state = 'rising'
                    
            if state == 'rising':
                if dataset[i]['height'] < dataset[i-1]['height']:
                    #logger.debug("{} {:.1f}m - High tide".format(dataset[i-1]['time'],dataset[i-1]['height']))
                    heightPretty = "{:.1f}m".format(dataset[i-1]['height'])
                    tides.append({'time':dataset[i-1]['time'], 'height':dataset[i-1]['height'], 'type':'High tide', 'heightPretty':heightPretty})
                    state = 'dropping'
                
            if dataset[i]['height'] == dataset[i-1]['height']:
                logger.info("Two adjacent tides with height {}m".format(dataset[i]['height']))
                    
        return tides
    
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    ts = TideScraper()
    data,location = ts.scrapeTideForecast(['Aberystwyth','Clarach','Borth'],bestguess="Aberystwyth")
    today = ts.getTides(data,"24-04-2015")
    for tide in today:
        print tide