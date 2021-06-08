# To run this in Docker, we have to run a different container running the Selenium.Firefox browser
#    docker run -d -p 4444:4444 selenium/standalone-firefox    (I then renamed it in Portainer)
#    http://127.0.0.1:4444/wd/hub/static/resource/hub.html     (this should be up and running)
# https://stackoverflow.com/questions/45323271/how-to-run-selenium-with-chrome-in-docker (substituted Firefox as needed)
#
# In Docker...
#   BIND the /db directory to a local directory for DB visibility.   Jobs.DB is NOT included in the DOCKERFILE and
#       will need to be manually copied to the local directory.   Use a SQLite browser to edit the Sites table in
#       the database.
#   BIND /etc/localtime and /etc/timezone to make sure container has correct time.
#   SET Environment variables:
#       IMAP_SERVER (mail.server.com)
#       IMAP_LOGIN (typically email address)
#       IMAP_PWD (password)
#       EMAIL_ADDRESS (email@domain.com)
#       PRODUCTION (value 'true')  will look for sites with 'A' (active) status and loop every 4 hours
#         Non-prod (value 'false) will look for sites with a 'P' (pending) status and will only execute once and exit.
#
# TODO:  Smashfly profile - locations brings back a list of locations, need to figure out how to parse on one line.

from bs4 import BeautifulSoup    # RUN pip3 install beautifulsoup4==4.9.3
from selenium import webdriver   # RUN pip3 install selenium==3.141.0
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

import datetime
import sqlite3
import imaplib
import email.message
import time  # for sleep
import os               # to get environment variables


# Set some global variables
site_id = ''
site_url = ''
site_type = ''
site_last_scan_date = ''
site_times_scanned_today = ''
site_description = ''
site_pattern_id = 0

job_title = ''
job_req = ''
job_location = ''
job_posted = ''
job_url = ''

max_pages = 2

##########################################
# SUBROUTINES GO HERE
##########################################

def scan_by_pattern():

    #scan_tenet()

    global job_title                                # these global variables might/will be changed
    global job_req
    global job_location
    global job_posted
    global job_url

    sql = "SELECT " \
        "pattern_name, search_code, dropdown_code, page_results_code, " \
        "popup_code, data_rows_code, title_code, title_page, req_code, req_page, " \
        "posted_code, posted_page, location_code, location_page, url_code, url_page, " \
        "crawl " \
        "FROM patterns " \
        "WHERE pattern_id=" + str(site_pattern_id) + ";"

    cursor.execute(sql)
    patterns = cursor.fetchall()
    if len(patterns) == 0:
        print("!!! ERROR Pattern not found for Site_Description = ", site_description, "...SQL=", sql)
        return

    pattern = patterns[0]               # there can be only ONE
    #print(pattern)

    pattern_name = pattern[0]
    search_code = pattern[1]
    dropdown_code = pattern[2]
    page_results_code = pattern[3]
    popup_code = pattern[4]
    data_rows_code = pattern[5]
    title_code = pattern[6]
    title_page = pattern[7]
    req_code = pattern[8]
    req_page = pattern[9]
    posted_code = pattern[10]
    posted_page = pattern[11]
    location_code = pattern[12]
    location_page = pattern[13]
    url_code = pattern[14]
    url_page = pattern[15]
    crawl = str(pattern[16]).lower()

    print("Site =", site_url)
    print("Pattern =", pattern_name)
    #browser.fullscreen_window()
    browser.get(site_url)
    time.sleep(2)                   #TODO put in better wait code
    browser.execute_script("window.scrollTo(0, document.body.scrollHeight/4);")        # page down 25%


    soup = BeautifulSoup(browser.page_source, "html.parser")

    # See if there is a pop-up to contend with
    #           browser.find_element_by_class_name('closeNotiIcon').click()     #gets error cannot scroll into view
    #
    # https://stackoverflow.com/questions/49045221/selenium-the-element-could-not-be-scrolled-into-view
    #       driver.execute_script("arguments[0].click();", element)      (example in Stackoverflow)
    #       browser.execute_script("arguments[0].click();", browser.find_element_by_class_name('closeNotiIcon'))

    if popup_code:
        try:
            # print("popup_code = ", popup_code)
            foo = eval(popup_code)
            print("popup clicked")
        except Exception as e:
            print("!!! WARNING Could not click on popup.  Will try to continue.  Code=", popup_code)
            print("Error = ", e)

    # Is there a dropdown to click (could be sort or records per page)
    if dropdown_code:
        try:
            foo = eval(dropdown_code)
            time.sleep(2)
            soup = BeautifulSoup(browser.page_source, "html.parser")
            print("dropdown menu clicked; html refreshed")

        except Exception as e:
            print("!!! WARNING Could not click dropdown menu as expected.  Will try to continue.  Code=", dropdown_code)
            print("Error = ", e)

    # Do we need to enter a search on the screen?
    if site_search:
        try:
            print("search found to enter")
            searchbox = eval(search_code)               # the search_code will return a reference to the search box
            searchbox.send_keys(site_search)
            actions = ActionChains(browser)
            actions.send_keys(Keys.ENTER).perform()
            time.sleep(3)
            soup = BeautifulSoup(browser.page_source, "html.parser")
            print("search entered; html refreshed")
        except Exception as e:
            print("!!! WARNING Could not enter search as expected.  Will try to continue.  Code=", search_code)
            print("Error = ", e)


    jobs = []                          # start with a blank list of jobs for this site
    paging = True                      # assume paging, at least 1 page
    pages = 0

    while paging:
        pages += 1
        rows = eval(data_rows_code)     # Get the results from the current page

        for row in rows:
            # print(row)

            job_title = ''              # start blank, make sure there are no accidents
            job_req = ''
            job_location = ''
            job_posted = ''
            job_url = ''

            if title_page == 1:     #TODO, make title only on page 1 (remove title_page from database)
                try:
                    job_title = eval(title_code)
                except Exception as e:
                    print("!!! WARNING - Error parsing job title.  Skipping job.  Error- ", e, "...Row data=", row)
                    job_title = ""
                    continue            # next job
            if req_page == 1:
                try:
                    job_req = eval(req_code)
                except Exception as e:
                    print("!!! WARNING - Error parsing job requisition; will use blank.  Error- ", e, "...Row data=", row)
                    job_req = ""
            if location_page == 1:
                try:
                    job_location = eval(location_code)
                except Exception as e:
                    print("!!! WARNING - Error parsing location; will use blank.  Error- ", e, "...Row data=", row)
                    job_location = ""
            if posted_page == 1:
                try:
                    job_posted = eval(posted_code)
                except Exception as e:
                    print("!!! WARNING - Error parsing posted date; will use blank.  Error- ", e, "...Row data=", row)
                    job_posted = ""
            if url_page == 1:
                try:
                    job_url = eval(url_code)
                    if job_url[:1] == '/':                     # if a relative link, then add the base part
                        job_url = base_url + job_url
                except Exception as e:
                    print("!!! WARNING - Error parsing URL; will use site_url.  Error- ", e, "...Row data=", row)
                    job_url = site_url
            if job_url == '':                                  # if still not found, then default back to site_url
                job_url = site_url

            job = {}            # Build a dictionary object of all the values that we have so far
                                # Will put onto the jobs[] list to pass onto the next phase
            job['title'] = job_title
            job['req'] = job_req
            job['location'] = job_location
            job['posted'] = job_posted
            job['url'] = job_url
            #print("job=", job)
            jobs.append(job)

        ##########################
        # Go to the next page?
        ##########################
        if page_results_code:
            try:
                foo = eval(page_results_code)
                time.sleep(2)
                soup = BeautifulSoup(browser.page_source, "html.parser")
                print("paging button pressed on page =", pages)
            except Exception as e:
                if pages == 1:
                    print("!!! WARNING.  Could not find/click the paging button on first page.  Code = ",
                          page_results_code)
                    print("Error = ", e)
                    # time.sleep(30)
                else:
                    print("Paging button no longer found.  Pages read = ", pages)
                paging = False
        else:
            print("Results Paging not enabled.  Only first page read. ")
            paging = False

        if pages >= max_pages:
            print("Max pages reached.  Pages=", pages)
            paging = False

    #########################################################################################
    # 2nd phase is to crawl each url and get the attibutes that were not on the first page
    #########################################################################################
    if crawl == "true":
        for job in jobs:
            job_title = job['title']
            job_req = job['req']
            job_location = job['location']
            job_posted = job['posted']
            job_url = job['url']

            print("...crawling to ", job_url)
            browser.get(job_url)
            time.sleep(2)                   # TODO put in better wait code

            soup = BeautifulSoup(browser.page_source, "html.parser")

            if title_page == 2:     #TODO, make title only on page 1 (remove title_page from database)
                try:
                    job_title = eval(title_code)
                except Exception as e:
                    print("!!! WARNING - Error parsing job title.  Skipping job.  Error- ", e, "...Row data=", row)
                    job_title = ""
                    continue            # next job
            if req_page == 2:
                try:
                    job_req = eval(req_code)
                except Exception as e:
                    print("!!! WARNING - Error parsing job requisition; will use blank.  Error- ", e, "...Row data=", row)
                    job_req = ""
            if location_page == 2:
                try:
                    job_location = eval(location_code)
                except Exception as e:
                    print("!!! WARNING - Error parsing location; will use blank.  Error- ", e, "...Row data=", row)
                    job_location = ""
            if posted_page == 2:
                try:
                    job_posted = eval(posted_code)
                except Exception as e:
                    print("!!! WARNING - Error parsing posted date; will use blank.  Error- ", e, "...Row data=", row)
                    job_posted = ""
            if url_page == 2:
                try:
                    job_url = eval(url_code)
                except Exception as e:
                    print("!!! WARNING - Error parsing URL; will use site_url.  Error- ", e, "...Row data=", row)
                    job_url = site_url

    #########################################
    # 3rd phase is to save it to the database
    #########################################
    job_count = len(jobs)
    for job in jobs:
        job_title = job['title']
        job_req = job['req']
        job_location = job['location']
        job_posted = job['posted']
        job_url = job['url']

        print("**********************")
        print("JOB TITLE=", job_title)
        print("JOB REQ=", job_req)
        print("JOB LOCATION=", job_location)
        print("JOB POSTED", job_posted)
        print("JOB URL=", job_url)

        save_job()
    print("*********************************")
    print("Total jobs examined:", job_count)
    update_site()




def save_job():

    # If we don't have a job title value, then something went really wrong.  Skip this routine.
    if job_title == '':
            print("!!! WARNING - Job title value was missing.  Skipping save_job routine....")
            return

    # See if the job has already been logged.  Return if so.
    sql = "SELECT count(*) " \
            "FROM Jobs " \
            "WHERE Site_Id = " + str(site_id)

    # if there is a job_req present, go by that
    if job_req != '':
        sql = sql + " AND Job_Req = '" + job_req + "'"
    else:                       # otherwise, go by job title + job posting date
        sql = sql + " AND Job_Title = '" + job_title + "' " \
            " AND Job_Posted='" + job_posted + "'"
    #print("duplicate check sql =", sql)


    cursor.execute(sql)
    job_count = cursor.fetchone()
    #print("job count=", job_count)
    if job_count[0] > 0:
        print("Duplicate job found.  Skipping save_job routine...")
        return

    # Save the job to the database
    sql = "INSERT INTO Jobs ('Site_ID','Job_Title','Job_Posted','Job_Req','Job_Location','Job_URL', 'Job_Inserted') " \
        "VALUES (" \
        " " + str(site_id) + ", " \
        "'" + job_title + "', " \
        "'" + job_posted + "', "  \
        "'" + job_req + "', " \
        "'" + job_location + "', " \
        "'" + job_url + "', " \
        "'" + run_dt + "') "

    #print("INSERT JOBS SQL =", sql)
    try:
        cursor.execute(sql)
        dbcon.commit()
        print("Job saved to database.")
    except Exception as e:
        print("!!! INSERT ERROR - Could not insert new job.  SQL='" + sql + ". Error: " + str(e))

def update_site():

    # Site variables already populated in main routine, but 2 will be changed, set global
    global site_last_scan_date
    global site_times_scanned_today

    if site_last_scan_date != today:        # reset the date/times if this is the first time today
        site_last_scan_date = today
        site_times_scanned_today = 1
    else:
        site_times_scanned_today += 1       # increment the times

    sql = "update sites SET " \
        "Site_Last_Scan_Date='" + site_last_scan_date + "', " \
        "Site_Times_Scanned_Today=" + str(site_times_scanned_today) + " " \
        "WHERE " \
        "Site_ID=" + str(site_id) + ";"
    cursor.execute(sql)
    dbcon.commit()
    print("Site updated.", site_description)

def send_email():

    sql = "select S.Site_Description, J.Job_Title, J.Job_Inserted, J.Job_Req, J.Job_Posted, J.Job_URL, J.Job_Location "\
        "from Jobs J, Sites S " \
        "where J.Site_Id=S.Site_Id "

    # If the time > 8pm, then send the whole day's findings
    if int(hour) > 19:          # Get everything from today
        emailsubject="JOB Postings Summary for " + today
        sql += "AND Job_Inserted > '" + today + "';"
    else:                       # Get just the lat run
        emailsubject="JOB Postings Incremental for " + run_dt
        sql += "AND Job_Inserted = '" + run_dt + "';"

    # otherwise, just send what was found in this run

    cursor.execute(sql)
    jobs = cursor.fetchall()

    if len(jobs) == 0:
        print("No jobs were found on this run.  Email cancelled.")
        return

    # start the HTML w/ header
    html = "<html><table width=100%><tr>" \
        "<td><b>Company</b</td>" \
        "<td><b>Job Title</b</td>" \
        "<td><b>Date Posted</b</td>" \
        "<td><b>Date Found</b</td>" \
        "</tr>"

    # will trigger the company row
    previous_company=""

    for job in jobs:
        company = job[0]    # Capture all the values
        title = job[1]
        inserted = job[2][:16]
        req = job[3]
        posted = job[4]
        url = job[5]
        location = job[6]

        if company != previous_company:         # change in company, write out company header
            html += "<tr width=100%><td>" + company + "</td></tr>"
            previous_company = company

        html += "<tr><td>&nbsp;</td>"
        html += "<td><a href='" + url + "'>" + title + "</a></td>"
        # html += "<td>" + req + "</td>"
        html += "<td>" + posted + "</td>"
        html += "<td>" + inserted + "</td>"
        # html += "<td>" + location + "</td>"
        html += "</tr>"

    # Finish the html
    html += "</table></html>"

    # Connect to INBOX
    #print(imapserver, userid, myemailaddress)          #print out credentials to make sure I got them

    mailbox = imaplib.IMAP4_SSL(imapserver)
    mailbox.login(userid, pd)

    # Create an email
    emailflag = ""  # no flags        emailflag = "\FLAGGED"

    new_message = email.message.Message()
    new_message["To"] = myemailaddress
    new_message["From"] = myemailaddress
    new_message["Subject"] = emailsubject
    new_message.add_header('Content-Type', 'text/html')
    new_message.set_payload(html)
    mailbox.append("INBOX", emailflag, imaplib.Time2Internaldate(time.time()), str(new_message).encode('utf-8'))

    print("Email sent")

    # Logout of mailbox
    mailbox.logout()


##########################################
# MAIN
##########################################

# Get secrets from environment variables
# In Pycharm, select the "Edit Configuration" menu item in the project drop-down box in top menu bar
imapserver = os.environ.get("IMAP_SERVER")
userid = os.environ.get("IMAP_LOGIN")
pd = os.environ.get("IMAP_PWD")
myemailaddress = os.environ.get("EMAIL_ADDRESS")
# print(imapserver, userid, myemailaddress)          #print out credentials to make sure I got them


# Connect to database
try:
    dbcon = sqlite3.connect('./db/jobs.db')
    print("Database connected")
except Exception as e:
    print("!!! ERROR Database NOT connected.  Error=" + str(e))
    quit()

# GET the environment variable  (PROD vs NONPROD)
prod = os.environ.get("PRODUCTION").lower()

while True:             # Forever loop (PROD only, drops out after one loop for NON-PROD)

    # Open the browser
    # browser = webdriver.Firefox(executable_path='/home/robert/Downloads/gecko/geckodriver')  # specific path to driver
    # browser = webdriver.Firefox(executable_path='./geckodriver')                          # driver with script
    if prod == "true":                      # Use Docker service for PROD
        browser = webdriver.Remote("http://127.0.0.1:4444/wd/hub", DesiredCapabilities.FIREFOX)  # Docker browser
    else:                                   # Use local Firefox to see what's happening
        browser = webdriver.Firefox()  # driver somewhere in path

    # capture the time of the run (all entries will have same timestamp for this run)
    run_dt = str(datetime.datetime.now())               # full timestamp
    today = str(datetime.datetime.now())[:10]           # just the date
    hour = datetime.datetime.now().strftime("%H")       # just the hour (will control what kind of email is sent)
    print("Run at ", run_dt)

    # Get a list of sites to crawl....stagger, stagger
    cursor = dbcon.cursor()
    sql = "SELECT Site_ID, Site_URL, Site_Type, Site_Last_Scan_Date, Site_Times_Scanned_Today, Site_Description, " \
          "Site_Search, Site_Pattern_ID " \
          "FROM Sites " \
          "WHERE Site_Status='A' "

    #print(sql)

    try:
        cursor.execute(sql)
        sites = cursor.fetchall()
    except Exception as e:
        print("!!! Fatal ERROR retrieving sites ", e)
        time.sleep(60)
        quit()


    for site in sites:
        site_id = site[0]                      #Capture all the values
        site_url = site[1]
        base_url = site_url[0:site_url.find("/", 8)]                     # grab the base URL
        site_type = site[2]
        site_last_scan_date = site[3]
        site_times_scanned_today = site[4]
        site_description = site[5]
        site_search = site[6]
        site_pattern_id = site[7]

        #if Site_Last_Scan_Date = today AND Site_Times_Scanned_Today > 10 THEN Continue (SKIP THIS ITERATION)

        if site_type == "pattern":
            scan_by_pattern()                # Should be the primary way

        if site_type == "Workday":
            scan_workday()

        if site_type == "Santander":
            scan_santander()

        if site_type == "Oracle":
            scan_oracle_cloud()

        if site_type == "smashfly":
            scan_smashfly()

        if site_type == "paycommonline":
            scan_paycommonline()

        if site_type == "cbre":
            scan_cbre()

        if site_type == "kpmg":
            scan_kpmg()

        if site_type == "phenom":
            scan_phenom()

        if site_type == "solis":
            scan_solis()

        if site_type == "tenet":
            scan_tenet()

        if site_type == "usaa":
            scan_tenet()


    # Send the report to INBOX, only for PROD
    if prod == "true":
        send_email()

    # Clean up
    browser.close()

    # sleep for awhile if production, else quit after one loop
    if prod == "true":
        print("sleeping...")
        time.sleep(14400)       # four hours
    else:
        break                   # out of forever loop

quit()          # Don't go past here

##########################################################
# SAMPLE CODE, Parking Lot, Obsolete below; cannot be run
###########################################################

def cellar():

    def template_simple():

        # Does not crawl

        global job_title                                # these global variables might/will be changed
        global job_req
        global job_location
        global job_posted
        global job_url

        print(site_url)
        browser.get(site_url)
        time.sleep(2)

        soup = BeautifulSoup(browser.page_source, "html.parser")
        rows = soup.find_all("div", {'class': 'article__header__text'})                  # build iterable of rows

        for row in rows:

            # row is the anchor (a) tag


            job_title = row
            job_req = row
            job_location = row
            job_posted = row
            job_url = row

            print("**********************")
            print("JOB TITLE=", job_title)
            print("JOB REQ=", job_req)
            print("JOB LOCATION=", job_location)
            print("JOB POSTED", job_posted)
            print("JOB URL=", job_url)

            #save_job()
        update_site()

    def template_page_and_crawl():

        # CRAWLS!   Press the NEXT button until it doesn't exist, building a list of URLs to crawl

        global job_title                                # these global variables might/will be changed
        global job_req
        global job_location
        global job_posted
        global job_url


        print(site_url)
        browser.get(site_url)
        time.sleep(2)

        # Page through all the results until the NEXT button is no longer there
        urls = []
        while True:

            soup = BeautifulSoup(browser.page_source, "html.parser")
            rows = soup.find_all("tag", {'attrib': 'value'})                   # build iterable of rows

            for row in rows:            # Build a list of URLs + plus whatever might be available on first page

                payload = []                                 # payload will be url,
                url = row.find("a")['href']
                title = row.find("a").contents[0]
                location = row.find("span").contents[0].strip()

                payload.append(url)
                payload.append(title)
                payload.append(location)
                urls.append(payload)

            try:
                next = browser.find_element_by_class_name("next")           # find the next button
                next.click()
                time.sleep(1)
            except:
                print("Next button no longer found.")
                break

        for payload in urls:

            # unpackage the payload    [url, job title, location]
            job_url = payload[0]
            job_title = payload[1]
            job_location = payload[2]

            browser.get(job_url)
            time.sleep(2)

            soup = BeautifulSoup(browser.page_source, "html.parser")

            job_req = soup.find_all("li", {'class': 'job-id job-info'})[0].contents[1]
            job_posted = soup.find_all("li", {'class': 'job-id job-info'})[1].contents[1]


            print("**********************")
            print("JOB TITLE=", job_title)
            print("JOB REQ=", job_req)
            print("JOB LOCATION=", job_location)
            print("JOB POSTED", job_posted)
            print("JOB URL=", job_url)

            # save_job()
        update_site()

    def eval_poc():
        # POC
        x = 100
        dynamic_code = "x * 5"
        y = eval(dynamic_code)
        print("results:", y)

        # EVAL POC
        #rows_code = "soup.find('table', {'id': 'jobs_table'}).find_all('tr')"
        #job_title_code = "row.find('a', {'class': 'job_title_link'}).contents[0]"

    def scan_tenet():
        ###############################
        # PAGES and CRAWLS
        ################################
        # Rows identifier:        rows = soup.find("section", {'id': 'search-results-list'}).find_all('li')
        # Flow:
        # 1. Build array of URLs on page.   Also get REQ, TITLE, and LOCATION
        # 2. Check for a disabled NEXT button.                                        <a class="next disabled>
        # 3. Press the NEXT button if NOT disabled.  Repeat build of URL array.
        # 4. Open each URL and get REQ and POSTED
        # TODO:  Why get REQ twice?


        global job_title                                # these global variables might/will be changed
        global job_req
        global job_location
        global job_posted
        global job_url

        print(site_url)
        browser.get(site_url)
        time.sleep(2)

        # Page through all the results until the NEXT button is no longer there
        urls = []
        while True:

            soup = BeautifulSoup(browser.page_source, "html.parser")
            rows = soup.find("section", {'id': 'search-results-list'}).find_all('li')                   # build iterable of rows

            for row in rows:            # Build a list of URLs + plus whatever might be available on first page
                # print("row=", row)
                anchor = row.find("a")                       # data is in the anchor tag

                payload = []                                 # payload will be url, req, title, location
                url = base_url + anchor['href']                    # attrib in the anchor tag
                req = anchor.get('data-job-id', '')                # attrib in the anchor tag
                title = anchor.find("h2").contents[0]              # heading in the anchor tag
                location = anchor.find(class_="job-location").contents[0]   # could be in a P or SPAN tag

                payload.append(url)
                payload.append(req)
                payload.append(title)
                payload.append(location)

                urls.append(payload)

            try:                    #Click the GDPR button if it exsits, obscures the NEXT button
                gdpr = browser.find_element_by_id('gdpr-button')
                gdpr.click()
            except:
                print("FYI...GDPR button not found")
            try:                                   # If the "next disabled" button exists, then exit the loop
                foo = soup.find("a", {'class': 'next disabled'})
                break  # exit the forever loop
            except Exception as e:
                print("FYI...more pages expected....", e)

            next = browser.find_element_by_class_name("next")  # find the next button
            next.click()
            time.sleep(1)

        for payload in urls:

            # unpackage the payload    [url, req, job title, location]
            job_url = payload[0]
            job_req = payload[1]
            job_title = payload[2]
            job_location = payload[3]

            browser.get(job_url)
            time.sleep(2)

            soup = BeautifulSoup(browser.page_source, "html.parser")

            # job_req = soup.find("li", {'class': 'job-id job-info'}).contents[1]
            # job_posted = soup.find("li", {'class': 'job-date job-info'}).contents[1]
            job_req = soup.find(class_='job-id job-info').contents[1]           #could be in LI or SPAN tag
            job_posted = soup.find(class_='job-date job-info').contents[1]


            print("**********************")
            print("JOB TITLE=", job_title)
            print("JOB REQ=", job_req)
            print("JOB LOCATION=", job_location)
            print("JOB POSTED", job_posted)
            print("JOB URL=", job_url)

            save_job()
        update_site()

    def scan_solis():

        tester()
        return


        ###############################
        # SIMPLE
        ################################
        # Rows identifier:       soup.find("table", {'id': 'jobs_table'}).find_all("tr")
        # Flow:
        # 1. Scan attribute from page 1
        #
        # REQ is N/A

        global job_title                                # these global variables might/will be changed
        global job_req
        global job_location
        global job_posted
        global job_url

        print(site_url)
        browser.get(site_url)
        time.sleep(3)

        soup = BeautifulSoup(browser.page_source, "html.parser")
        rows = soup.find("table", {'id': 'jobs_table'}).find_all("tr")           # build rows

        for row in rows:
            #print(row)
                                             # first row does not contain any data (headings)
            try:
                job_title = row.find('a', {'class': 'job_title_link'}).contents[0]
                job_req = ""                                   # no identifier
                job_location = row.find_all("td")[1].contents[0].strip()    # in the 2nd TD tag
                job_posted = ""                                # date is not posted
                job_url = base_url + row.find('a', {'class': 'job_title_link'})['href']
            except Exception as e:
                print("!!! WARNING - Error parsing Solis row.  Error- ", e, "...Row data=", row)
                job_title = ""
                job_req = ""
                job_location = ""
                job_posted = ""
                job_url = ""
                continue

            print("**********************")
            print("JOB TITLE=", job_title)
            print("JOB REQ=", job_req)
            print("JOB LOCATION=", job_location)
            print("JOB POSTED", job_posted)
            print("JOB URL=", job_url)

            save_job()
        update_site()

    def scan_phenom():              # Soutwest, Baylor
        ###############################
        # SORT and SCAN RESULTS
        ################################
        # Rows identifier:        rows = soup.find_all("a", {'ph-tevent': 'job_click'})
        # Flow:
        # 1. Sort by RECENT
        # 2. Read attributes from page 1
        #
        # TODO:  Could add paging

        global job_title                                # these global variables might/will be changed
        global job_req
        global job_location
        global job_posted
        global job_url

        print(site_url)
        browser.get(site_url)
        time.sleep(2)

        # Click on the SORT Drop down and select 'Recent'
        # https://sqa.stackexchange.com/questions/1355/what-is-the-correct-way-to-select-an-option-using-seleniums-python-webdriver
        select = browser.find_element_by_xpath("//select[@id='sortselect']/option[@value='Most recent']").click()
        time.sleep(2)

        soup = BeautifulSoup(browser.page_source, "html.parser")
        rows = soup.find_all("a", {'ph-tevent': 'job_click'})                        # isolate the data

        for row in rows:

            job_title = row.get('data-ph-at-job-title-text', '')
            job_req = row.get('data-ph-at-job-id-text', '')
            job_location = row.get('data-ph-at-job-location-text', '')
            job_posted = row.get('data-ph-at-job-post-date-text', '')
            job_url = row['href']

            print("**********************")
            print("JOB TITLE=", job_title)
            print("JOB REQ=", job_req)
            print("JOB LOCATION=", job_location)
            print("JOB POSTED", job_posted)
            print("JOB URL=", job_url)

            save_job()
        update_site()

    def scan_kpmg():


        ###############################
        # PAGES and CRAWLS
        ################################
        # Rows identifier:        rows = soup.find("section", {'id': 'search-results-list'}).find_all('li')
        # Flow:
        # 1. Build array of URLs on page.   Also TITLE
        # 2. Check if NEXT button exists                                       find_element_by_link_text("Next >>")
        # 3. If exists, click NEXT and repeat step 1
        # 4. Open each URL and get other attributes
        #
        # Job posted is N/A

        global job_title                                # these global variables might/will be changed
        global job_req
        global job_location
        global job_posted
        global job_url

        print(site_url)
        browser.get(site_url)
        time.sleep(2)

        # Page through all the results until the NEXT button is no longer there
        urls = []
        while True:

            soup = BeautifulSoup(browser.page_source, "html.parser")
            rows = soup.find("div", {'class': 'listSingleColumn'}).find_all("div", {'class': 'resultsData'})

            for row in rows:
                payload = []                                 # payload will be url, job title
                url = row.find("a")['href']
                title = row.find("a").contents[0]
                # location = row.find("span").contents[0].strip()
                # print("location=", location)
                payload.append(url)
                payload.append(title)
                urls.append(payload)

            try:
                next = browser.find_element_by_link_text("Next >>")
            except:
                print("Next button no longer found.")
                break

            next.click()
            time.sleep(1)


        for payload in urls:

            # unpackage the payload    [url, job title]
            job_url = payload[0]
            job_title = payload[1]

            browser.get(job_url)
            time.sleep(2)

            soup = BeautifulSoup(browser.page_source, "html.parser")

            job_req = soup.find("div", {'class': 'jobData'}).find_all("p")[0].contents[1]
            job_location = soup.find("div", {'class': 'jobData'}).find_all("p")[2].contents[1]

            job_posted = ""                     # date is not posted


            print("**********************")
            print("JOB TITLE=", job_title)
            print("JOB REQ=", job_req)
            print("JOB LOCATION=", job_location)
            print("JOB POSTED", job_posted)
            print("JOB URL=", job_url)

            save_job()
        update_site()

    def scan_cbre():

        # Does not crawl
        # Only 6 record on first page

        global job_title                                # these global variables might/will be changed
        global job_req
        global job_location
        global job_posted
        global job_url

        print(site_url)
        browser.get(site_url)
        time.sleep(2)

        soup = BeautifulSoup(browser.page_source, "html.parser")
        data = soup.find("div", {'class': 'section__content__results'})                # isolate the data
        rows = data.find_all("div", {'class': 'article__header__text'})                  # build iterable of rows

        for row in rows:

            # row is the anchor (a) tag

            #print("UL=", ul)
            #continue

            job_title_a = row.find('a')             # grab the anchor that contains title and url
            moreinfo_div = row.find('div', {'class': 'article__header__text__subtitle'})
            moreinfo_spans = moreinfo_div.find_all('span')

            # row.find('div', {'class': 'article__header__text__subtitle'}).find_all('span')[0].contents[0].strip()

            job_title = job_title_a.contents[0].strip()
            job_req = moreinfo_spans[0].contents[0].strip()
            job_location = moreinfo_spans[2].contents[0].strip()
            job_posted = moreinfo_spans[1].contents[0].strip()
            job_url = row.find('a')['href']

            print("**********************")
            print("JOB TITLE=", job_title)
            print("JOB REQ=", job_req)
            print("JOB LOCATION=", job_location)
            print("JOB POSTED", job_posted)
            print("JOB URL=", job_url)

            save_job()
        update_site()

    def scan_paycommonline():

        # Does not crawl
        # Does not have a date
        # Does not have a req

        global job_title                                # these global variables might/will be changed
        global job_req
        global job_location
        global job_posted
        global job_url

        print(site_url)
        browser.get(site_url)
        time.sleep(2)

        soup = BeautifulSoup(browser.page_source, "html.parser")
        data = soup.find("div", {'id': 'results'})                                        # isolate the data
        rows = data.find_all("a", {'class': 'JobListing__container'})                  # build iterable of rows

        for row in rows:

            job_title = row.find("span", {'class': 'jobInfoLine jobTitle'}).contents[0]
            job_req = ""  # no posted identifier
            job_location = row.find("span", {'class': 'jobInfoLine jobLocation JobListing__subTitle'}).contents[0]
            job_posted = ""  # no posted date
            job_url = base_url + row['href']

            print("**********************")
            print("JOB TITLE=", job_title)
            print("JOB REQ=", job_req)
            print("JOB LOCATION=", job_location)
            print("JOB POSTED", job_posted)
            print("JOB URL=", job_url)

            save_job()
        update_site()

    def scan_smashfly():


        # Does not crawl
        # Does not have a date, sorts by job id DESC  #TODO:  Validate that sorting by jobid desc gets latest postings
        #

        global job_title                                # these global variables might/will be changed
        global job_req
        global job_location
        global job_posted
        global job_url
        job_posted = ""                                      # there is no posted date.

        print(site_url)
        browser.get(site_url)
        time.sleep(2)

        # Instead of a posted date, will click on the job id in desc; assumes highest is latest

        element = browser.find_element_by_link_text("Job ID")
        element.click()         # first click is ASC
        # time.sleep(1)           # rest a sec
        element.click()         # 2nd click is DESC
        time.sleep(1)           # give a second to reload

        soup = BeautifulSoup(browser.page_source, "html.parser")

        table = soup.find("div", {'class': 'k-grid-content'})            # isolate the data grid table
        ul_list = table.find_all("tr", {'role': 'row'})                  # build iterable of rows

        for ul in ul_list:

            job_req = ul.find("td", {'class': 'DisplayJobId-cell'}).contents[0]
            job_title_td = ul.find("td", {'class': 'JobTitle-cell'})
            job_title_a = job_title_td.find("a")
            job_title = job_title_a.contents[0]
            job_url = base_url + job_title_a['href']
            job_locations = []
            job_location_td = ul.find("td", {'class': 'LongTextField3-cell'})
            job_location_divs = job_location_td.find_all("div")
            for div in job_location_divs:
                #print("location div =", div)
                job_locations.append(div.contents[0].replace(",", " "))
            job_location = ",".join(job_locations)

            print("**********************")
            print("JOB TITLE=", job_title)
            print("JOB REQ=", job_req)
            print("JOB LOCATION=", job_location)
            print("JOB POSTED", job_posted)
            print("JOB URL=", job_url)

            save_job()
        update_site()

    def scan_oracle_cloud():

        global job_title                # these global variables might/will be changed
        global job_req
        global job_location
        global job_posted
        global job_url

        print(site_url)
        browser.get(site_url)
        time.sleep(2)
        soup = BeautifulSoup(browser.page_source, "html.parser")

        ul_list = soup.find_all("div", {'class': 'job-tile__info'})

        for ul in ul_list:

            #print("UL=", ul)

            job_title = ul.find("h2").contents[0]
            job_location = ul.find("span", {'data-bind': 'text: job.primaryLocation'}).contents[0]
            job_posted = ul.find("span", {'data-bind': 'text: job.postedDate'}).contents[0]
            job_req = ""                  # no job req identifiers available, blank it
            job_url = site_url            # no url, default back to the first page

            print("**********************")
            print("JOB TITLE=", job_title)
            print("JOB REQ=", job_req)
            print("JOB LOCATION=", job_location)
            print("JOB POSTED", job_posted)
            print("JOB URL=", job_url)

            save_job()
        update_site()

    def scan_santander():

        # Will get job title, job url, job location from the first page
        # Then open each link and get the job req and job date

        global job_title                # these global variables might/will be changed
        global job_req
        global job_location
        global job_posted
        global job_url

        url_list = []                                        # list of 2ndary pages to crawl
        # base_url = site_url[0:site_url.find("/", 8)]         # grab the base URL
        #print(base_url)

        browser.get(site_url)               # should get 15 jobs on page 1
        time.sleep(2)

        soup = BeautifulSoup(browser.page_source, "html.parser")

        alist = soup.find_all("a", href=True)                              # Examine all hyperlinks
        for a in alist:
            #print(a)

            if a['href'][:5] == "/job/":                         # Grab all the links that start with /job/
                #print(a)
                #print("job found", a['href'])

                job_url = base_url + a['href']                     # URL

                job_title = a.find("h2").contents[0]                        # job title
                #print("job_title=", job_title)

                #job_location = a.find("span", {'class': 'job-location'}).contents[0]        # job location
                job_locations = a.find("span", {'class': 'job-location'}).contents         # job location
                for payload in job_locations:                      # manually remove the <br/> tags out of the list
                    if str(payload) == "<br/>":
                        job_locations.remove(payload)
                job_location = ",".join(job_locations)             # join the list into a single string

                payload = []                            # save the urls in a format of [url,location, title]
                payload.append(job_url)
                payload.append(job_location)
                payload.append(job_title)
                url_list.append(payload)                       #...and put the payload in a list

        for payload in url_list:                # Crawl each url to get the details
            job_url = payload[0]                # Parse the payload
            job_location = payload[1]
            job_title = payload[2]

            #print(job_url)
            browser.get(job_url)               # should get 15 jobs on page 1
            time.sleep(2)

            soup = BeautifulSoup(browser.page_source, "html.parser")
            try:
                job_req = soup.find("span", {'class': 'job-id job-info'}).contents[1]
            except:
                #print(payload)
                print("!!! WARNING - 'job-id' tag not found.  Skipping subpage URL =", job_url)
                continue
            try:
                job_posted = soup.find("span", {'class': 'job-date job-info'}).contents[1]
            except:
                print(payload)
                print("!!! WARNING - 'job-date' tag not found.  Skipping record. Subpage URL =", job_url)
                continue

            print("**********************")
            print("Title =", job_title)
            print("Location =", job_location)
            print("Req =", job_req)
            print("Posted =", job_posted)
            print("URL =", job_url)

            save_job()              # Should have enough to persist the job
        update_site()

    def scan_workday():             #McKesson,  Salesforce
        # https://mckesson.wd3.myworkdayjobs.com/External_Careers

        global job_title                # these global variables might/will be changed
        global job_req
        global job_location
        global job_posted
        global job_url

        print(site_url)
        browser.get(site_url)

        timeout = 5
        try:
            element_present = EC.presence_of_element_located((By.ID, "wd-AdvancedFacetedSearch-SearchTextBox-input"))
            WebDriverWait(browser, timeout).until(element_present)
        except TimeoutException:
            print("Timed out waiting for page to load")
        finally:
            print("Page loaded")


        # If a site search, then do that
        if site_search:
            # print("search found")
            searchbox = browser.find_element_by_id('wd-AdvancedFacetedSearch-SearchTextBox-input')
            searchbox.send_keys(site_search)

            actions = ActionChains(browser)
            actions.send_keys(Keys.ENTER).perform()

            time.sleep(3)

        for i in range(1, 2):           # Scroll down a couple of times, wait a few seconds each page
            browser.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

        soup = BeautifulSoup(browser.page_source, "html.parser")
        rows = soup.find_all("li", {'data-automation-id': 'compositeContainer'})     #isolate the data
        for row in rows:

            try:
                job_title = row.find("div", {'data-automation-id': 'promptOption'}).get('title', '').replace("'", "`").strip()
                job_req = row.find("span", {'data-automation-id': 'compositeSubHeaderOne'}).get('title', '').split("|")[0].strip()
                job_location = row.find("span", {'data-automation-id': 'compositeSubHeaderOne'}).get('title', '').split("|")[1].strip()
                job_posted = row.find("span", {'data-automation-id': 'compositeSubHeaderOne'}).get('title', '').split("|")[2].strip()
                job_url = site_url                  # can't find direct link.  default back to the first page
            except Exception as e:
                print("!!! WARNING.  Error parsing Workday row.  Error =", e, "...Row data = ", row)
            finally:
                print("**********************")
                print("JOB TITLE=", job_title)
                print("JOB ID=", job_req)
                print("JOB LOCATION=", job_location)
                print("JOB POSTED", job_posted)
                print("JOB URL=", job_url)

            save_job()
        update_site()