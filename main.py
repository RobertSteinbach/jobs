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
#       PRODUCTION PROD will loop every 4 hours
#         Non-prod (value 'false) execute once and exit, puts a DEV tag on email subject, limits pages to 2
#
# TODO:  Smashfly pattern - locations brings back a list of locations, need to figure out how to parse on one line.
# TODO:  Extend the Errors table to contain a bad_url.  On details pass, check url and skip bad ones.
# TODO:  Clean up errors > 30 days old


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
import re               # needed!  will be used in code in the database


verbose = True             # debugging flag

# Set some global variables
site_id = ''
site_url = ''
site_last_scan_date = ''
site_times_scanned_today = ''
site_description = ''
site_pattern_id = 0

job_title = ''
job_req = ''
job_location = ''
job_posted = ''
job_url = ''

errmsg = ''                 # friendly error message
errors = []                 # keep a list of errors and then add them to database for posterity
err_dict = {}               # structured error dictionary.   Append to the errors[] list as we go.
                                # err_dict['err_msg_friendly'] = "this is a friendly message"
                                # err_dict['err_site'] = "this is the site name"
                                # err_dict['err_pattern'] = "this is the pattern name"
                                # err_dict['err_url'] = "this is the url in error"
                                # err_dict['err_code'] = "this is the custom code from the database"
                                # err_dict['err_msg_error'] = "this is the actual error message raised by the exception"


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
    global errmsg
    global errors
    global err_dict

    jobs = []                          # start with a blank list of jobs for this site
    paging = True                      # assume paging, at least 1 page
    pages = 0                          # keep track of the pages

    # Read some data about this site - PATTERN
    sql = "SELECT " \
        "pattern_name, search_code, dropdown_code, page_results_code, " \
        "popup_code, data_rows_code, title_code, req_code,  " \
        "posted_code, location_code, url_code, crawl " \
        "FROM patterns " \
        "WHERE pattern_id=" + str(site_pattern_id) + ";"
    cursor.execute(sql)
    patterns = cursor.fetchall()
    if len(patterns) == 0:
        errmsg = "!!! ERROR Pattern not found for Site_Description = " + site_description + "...SQL=" + sql
        print(errmsg)
        err_dict['err_msg_friendly'] = errmsg
        err_dict['err_site'] = site_description
        err_dict['err_pattern'] = ''
        err_dict['err_url'] = ''
        err_dict['err_code'] = ''
        err_dict['err_msg_error'] = ''
        errors.append(err_dict)
        return

    pattern = patterns[0]               # there can be only ONE
    pattern_name = pattern[0]
    search_code = pattern[1]
    dropdown_code = pattern[2]
    page_results_code = pattern[3]
    popup_code = pattern[4]
    data_rows_code = pattern[5]
    title_code = pattern[6]
    req_code = pattern[7]
    posted_code = pattern[8]
    location_code = pattern[9]
    url_code = pattern[10]
    crawl = str(pattern[11]).lower()

    # Read the list of previously scanned URLs - will not crawl those
    sql = "select job_URL FROM jobs where Site_Id=" + str(site_id) + ";"
    cursor.execute(sql)
    temp = cursor.fetchall()
    previous_urls = []
    for item in temp:
        previous_urls.append(item[0])
    #print("previous_urls=", previous_urls)
    del temp


    print("*********************************")
    print("Company =", site_description)
    print("URL =", site_url)
    print("Pattern =", pattern_name)
    #browser.fullscreen_window()
    try:
        browser.get(site_url)
    except Exception as e:
        errmsg = "!!! ERROR Could not open URL.  Skipping site."
        print(errmsg)
        err_dict['err_msg_friendly'] = errmsg
        err_dict['err_site'] = site_description
        err_dict['err_pattern'] = pattern_name
        err_dict['err_url'] = site_url
        err_dict['err_code'] = ''
        err_dict['err_msg_error'] = str(e)
        errors.append(err_dict)
        return

    time.sleep(2)                   #TODO put in better wait code
    # browser.execute_script("window.scrollTo(0, document.body.scrollHeight);")        # page to bottom
    soup = BeautifulSoup(browser.page_source, "html.parser")

    # When you really got to know....
    #print("********* SOUP ******************")
    #print(soup)
    #print("********** END SOUP *************")

    # See if there is a pop-up to contend with
    if popup_code:
        # if browser.find_element_by_id('ccpa-button'): browser.find_element_by_id('ccpa-button').click(); if browser.find_element_by_id('gdpr-button'): browser.find_element_by_id('gdpr-button').click()
        #           browser.find_element_by_class_name('closeNotiIcon').click()     #gets error cannot scroll into view
        #
        # https://stackoverflow.com/questions/49045221/selenium-the-element-could-not-be-scrolled-into-view
        #       driver.execute_script("arguments[0].click();", element)      (example in Stackoverflow)
        #       browser.execute_script("arguments[0].click();", browser.find_element_by_class_name('closeNotiIcon'))

        try:
            # TEST CODE - will test for a button and use javascript to click it
            #if browser.find_elements_by_class_name('onetrust-close-btn-handler'):
            # browser.execute_script("arguments[0].click();",
            # browser.find_element_by_class_name('onetrust-close-btn-handler'))
            # TEST CODE END

            if verbose: print("popup_code = ", popup_code)
            exec(popup_code)
            time.sleep(2)
            print("...popup clicked ok")
        except Exception as e:
            errmsg = "!!! WARNING Could not click on popup.  Will try to continue."
            print(errmsg)
            err_dict['err_msg_friendly'] = errmsg
            err_dict['err_site'] = site_description
            err_dict['err_pattern'] = pattern_name
            err_dict['err_url'] = site_url
            err_dict['err_code'] = popup_code
            err_dict['err_msg_error'] = str(e)
            errors.append(err_dict)


    # Is there a DROPDOWN to click (could be sort or records per page)    #TODO: maybe combine with popup_code?
    if dropdown_code:
        try:
            if verbose: print("dropdown code=", dropdown_code)
            exec(dropdown_code)

            time.sleep(2)
            soup = BeautifulSoup(browser.page_source, "html.parser")
            print("...dropdown menu clicked ok; html refreshed")

        except Exception as e:
            print()
            print("Error = ", e)
            errmsg = "!!! WARNING Could not click dropdown menu as expected.  Will try to continue."
            err_dict['err_msg_friendly'] = errmsg
            err_dict['err_site'] = site_description
            err_dict['err_pattern'] = pattern_name
            err_dict['err_url'] = site_url
            err_dict['err_code'] = dropdown_code
            err_dict['err_msg_error'] = str(e)
            errors.append(err_dict)
            print(errmsg)

    # Do we need to enter a SEARCH on the screen?
    if site_search and search_code:
        try:
            if verbose: print("search code = ", search_code)
            searchbox = eval(search_code)               # the search_code must return a reference to the search box
            searchbox.send_keys(site_search)
            actions = ActionChains(browser)
            actions.send_keys(Keys.ENTER).perform()
            time.sleep(5)
            soup = BeautifulSoup(browser.page_source, "html.parser")
            print("...search entered=", site_search)
        except Exception as e:
            errmsg = "!!! ERROR Could not enter search as expected.  Skipping site to reduce irrelevant postings."
            print(errmsg)
            err_dict['err_msg_friendly'] = errmsg
            err_dict['err_site'] = site_description
            err_dict['err_pattern'] = pattern_name
            err_dict['err_url'] = site_url
            err_dict['err_code'] = search_code
            err_dict['err_msg_error'] = str(e)
            errors.append(err_dict)
            paging = False          # this will cause 0 records to be found, but the site will be updated

    while paging:
        pages += 1                      # increment page count

        # Quick sanity check.
        if data_rows_code[:5] != "soup.":
            errmsg = "!!! ERROR - unexpected value in data_rows_code.  Skipping site. " \
                " Site=" + site_description + \
                " Pattern=" + pattern_name + \
                " URL=" + site_url + \
                " Code=" + data_rows_code
            err_dict['err_msg_friendly'] = errmsg
            err_dict['err_site'] = site_description
            err_dict['err_pattern'] = pattern_name
            err_dict['err_url'] = site_url
            err_dict['err_code'] = data_rows_code
            err_dict['err_msg_error'] = ''
            errors.append(err_dict)

            print(errmsg)
            paging = False       # nothing else should execute until the site is updated
            continue

        if verbose: print("data_rows_code =", data_rows_code)

        try:
            rows = eval(data_rows_code)     # Get the results from the current page
        except Exception as e:
            errmsg = "!!! ERROR - Error parsing data rows.  Skipping site. "
            err_dict['err_msg_friendly'] = errmsg
            err_dict['err_site'] = site_description
            err_dict['err_pattern'] = pattern_name
            err_dict['err_url'] = site_url
            err_dict['err_code'] = data_rows_code
            err_dict['err_msg_error'] = str(e)
            errors.append(err_dict)
            print(errmsg)

            paging = False       # stop paging.  if page 1, nothing else should execute until site is updated
            continue

        for row in rows:
            job_title = ''              # start blank, make sure there are no accidents
            job_req = ''
            job_location = ''
            job_posted = ''
            job_url = ''

            if verbose:
                print("*************************************")
                print("*** PHASE 1 - Read data row       ***")
                print("*************************************")
                print("row= ", row)

            #############################################################################################
            # URL can only be on page 1, get first...handy in case of error on the following attributes
            # ....but there may not be a code in the database (e.g. workday)
            #############################################################################################
            if str(url_code)[:3] == 'row':
                try:
                    job_url = eval(url_code)
                    if job_url[:1] == '/':                     # if a relative link, then add the base part
                        job_url = base_url + job_url
                    if verbose:
                        print("*** Job URL ***")
                        print('row.url=', job_url)
                        print("  >>url_code =", url_code)

                except Exception as e:
                    errmsg = "!!! WARNING - Error parsing job URL. "
                    print(errmsg)
                    err_dict['err_msg_friendly'] = errmsg
                    err_dict['err_site'] = site_description
                    err_dict['err_pattern'] = pattern_name
                    err_dict['err_url'] = site_url
                    err_dict['err_code'] = url_code
                    err_dict['err_msg_error'] = str(e)
                    errors.append(err_dict)

            ##########################################
            # TITLE - can only be on page 1
            ##########################################
            try:
                job_title = eval(title_code)
                if verbose:
                    print("*** Title ***")
                    print('row.title=', job_title)
                    print('  >>title_code=', title_code)

            except Exception as e:
                errmsg = "!!! WARNING - Error parsing job title.  Skipping job."
                print(errmsg)
                err_dict['err_msg_friendly'] = errmsg
                err_dict['err_site'] = site_description
                err_dict['err_pattern'] = pattern_name
                err_dict['err_url'] = job_url
                err_dict['err_code'] = title_code
                err_dict['err_msg_error'] = str(e)
                errors.append(err_dict)

                job_title = ""           # won't be written to the database anyway
                continue            # next job

            ##########################################
            # REQ - can be on page 1 or page 2
            ############################################
            if str(req_code).find('row.') > -1:
                try:
                    job_req = eval(req_code)
                    if verbose:
                        print("*** Req ***")
                        print('row.req =', job_req)
                        print("  >>req_code = ", req_code)

                except Exception as e:
                    errmsg = "!!! WARNING - Error parsing job requisition. "
                    print(errmsg)
                    err_dict['err_msg_friendly'] = errmsg
                    err_dict['err_site'] = site_description
                    err_dict['err_pattern'] = pattern_name
                    err_dict['err_url'] = job_url
                    err_dict['err_code'] = req_code
                    err_dict['err_msg_error'] = str(e)
                    errors.append(err_dict)

                    job_req = ""

            #################################################
            # LOCATION - can be on page 1 or page 2
            #################################################
            if str(location_code).find('row.') > -1:
                try:
                    job_location = eval(location_code)
                    if verbose:
                        print("*** Location ***")
                        print('row.location=', job_location)
                        print("  >>location_code = ", location_code)
                except Exception as e:
                    errmsg = "!!! WARNING - Error parsing location. "
                    print(errmsg)
                    err_dict['err_msg_friendly'] = errmsg
                    err_dict['err_site'] = site_description
                    err_dict['err_pattern'] = pattern_name
                    err_dict['err_url'] = job_url
                    err_dict['err_code'] = location_code
                    err_dict['err_msg_error'] = str(e)
                    errors.append(err_dict)

                    job_location = ""

            ##################################################
            # POSTED DATE- can be on page 1 or page 2
            ###################################################
            if str(posted_code).find('row.') > -1:
                try:
                    job_posted = eval(posted_code)
                    if verbose:
                        print("*** Posted Date ***")
                        print('row.posted=', job_posted)
                        print("  >>posted_code = ", posted_code)

                except Exception as e:
                    errmsg = "!!! WARNING - Error parsing posted date. "
                    print(errmsg)
                    err_dict['err_msg_friendly'] = errmsg
                    err_dict['err_site'] = site_description
                    err_dict['err_pattern'] = pattern_name
                    err_dict['err_url'] = job_url
                    err_dict['err_code'] = posted_code
                    err_dict['err_msg_error'] = str(e)
                    errors.append(err_dict)

                    job_posted = ""

            job = {}            # Build a dictionary object of all the values that we have so far
                                # Will put onto the jobs[] list to pass onto the next phase
            job['title'] = job_title
            job['req'] = job_req
            job['location'] = job_location
            job['posted'] = job_posted
            job['url'] = job_url
            if verbose: print("p1.job=", job)
            jobs.append(job)

        ##########################
        # Go to the next page?
        ##########################
        if page_results_code:
            try:
                if verbose:
                    print("****************************************")
                    print("*** PHASE 1.B - PAGE results (maybe) ***")
                    print("****************************************")
                    print("page_results_code = ", page_results_code)

                # TEST CODE
                # Original
                #browser.find_element_by_class_name('next-page-btn').click()
                #browser.find_element_by_class_name('next-page-btn').send_keys(Keys.ENTER)
                #actions = ActionChains(browser)
                #actions.send_keys(Keys.ENTER).perform()

                #print("about to try to scroll next button into view....waiting 5 seconds....")
                #time.sleep(5)
                #browser.execute_script('arguments[0].scrollIntoView(true);', btn)
                #browser.execute_script('arguments[0].scrollIntoView(false);', btn)
                #ActionChains(browser).move_to_element(btn).perform()
                #print("scrolling completed")
                #time.sleep(5)
                # TEST CODE END

                exec(page_results_code)
                time.sleep(2)
                soup = BeautifulSoup(browser.page_source, "html.parser")
                print("...paging button pressed on page =", pages)
            except Exception as e:
                print("...paging button no longer found.  Pages read = ", pages)
                if verbose:
                    print("paging error = ", e)
                paging = False          # stop paging
        else:
            if verbose:
                print("...results Paging not enabled.  Only first page read. ")
            paging = False

        if pages >= max_pages:
            print("...max pages reached.  Pages=", pages)
            paging = False

    # Paging completed
    # Give a progress of how many jobs were found in phase 1
    print("...number of job postings found =", len(jobs))

    #########################################################################################
    # 2nd phase is to CRAWL each url and get the attributes that were not on the first page
    #########################################################################################
    if verbose:
        print("***************************************")
        print("*** PHASE 2 - CRAWL results (maybe) ***")
        print("***************************************")
    if crawl == "true":
        jobs2 = []                      #create a new list for the 2nd phase, then overwrite the jobs list
        for job in jobs:

            job_title = job['title']
            job_req = job['req']
            job_location = job['location']
            job_posted = job['posted']
            job_url = job['url']

            print(job_title)                # show progress by job title
            if job_url in previous_urls:
                print("...url previously saved; skipping crawl and updating job_last_detected.")
                sql = "update jobs set job_last_detected='" + run_dt + "' WHERE " \
                "Site_Id=" + str(site_id) + " AND Job_URL='" + job_url + "' "
                if verbose: print("update previously crawled job sql=", sql)

                try:
                    cursor.execute(sql)
                    dbcon.commit()
                except Exception as e:
                    errmsg = "!!! UPDATE ERROR - Could not update previously crawled job"
                    print(errmsg)
                    err_dict['err_msg_friendly'] = errmsg
                    err_dict['err_site'] = site_description
                    err_dict['err_pattern'] = ''
                    err_dict['err_url'] = job_url
                    err_dict['err_code'] = sql
                    err_dict['err_msg_error'] = str(e)
                    errors.append(err_dict)

                continue  # next job

            print("...crawling to ", job_url)
            browser.get(job_url)
            time.sleep(2)                   # TODO put in better wait code

            detail = BeautifulSoup(browser.page_source, "html.parser")

            ##################################################
            # URL - can only be on page 1, not relevant here
            # TITLE - can only be on page 1, not relevant here
            ##################################################

            #######
            # REQ
            #######
            if str(req_code).find('detail.') > -1:
                try:
                    job_req = eval(req_code)
                    if verbose:
                        print("*** Req (detail page) ***")
                        print('detail.req=', job_req)
                        print('  >>req_code =', req_code)
                except Exception as e:
                    errmsg = "!!! WARNING - Error parsing job requisition on details page. "
                    print(errmsg)
                    err_dict['err_msg_friendly'] = errmsg
                    err_dict['err_site'] = site_description
                    err_dict['err_pattern'] = pattern_name
                    err_dict['err_url'] = job_url
                    err_dict['err_code'] = req_code
                    err_dict['err_msg_error'] = str(e)
                    errors.append(err_dict)

                    job_req = ""

            ################
            # LOCATION
            ################
            if str(location_code).find('detail.') > -1:
                try:
                    job_location = eval(location_code)
                    if verbose:
                        print("*** Location (detail page) ***")
                        print('detail.location=', job_location)
                        print("  >>location_code=", location_code)
                except Exception as e:
                    errmsg = "!!! WARNING - Error parsing location on details page. "
                    print(errmsg)
                    err_dict['err_msg_friendly'] = errmsg
                    err_dict['err_site'] = site_description
                    err_dict['err_pattern'] = pattern_name
                    err_dict['err_url'] = job_url
                    err_dict['err_code'] = location_code
                    err_dict['err_msg_error'] = str(e)
                    errors.append(err_dict)

                    job_location = ""

            ##################
            # DATE POSTED
            ###################
            if str(posted_code).find('detail.') > -1:
                try:
                    job_posted = eval(posted_code)
                    if verbose:
                        print("*** Date Posted (detail page) ***")
                        print('detail.posted=', job_posted)
                        print("  >>posted_code = ", posted_code)

                except Exception as e:
                    errmsg = "!!! WARNING - Error parsing posted date on details page. "
                    print(errmsg)
                    err_dict['err_msg_friendly'] = errmsg
                    err_dict['err_site'] = site_description
                    err_dict['err_pattern'] = pattern_name
                    err_dict['err_url'] = job_url
                    err_dict['err_code'] = posted_code
                    err_dict['err_msg_error'] = str(e)
                    errors.append(err_dict)

                    job_posted = ""

            # Update the job dictionary with potentially new values  (title and url will be unchanged)
            job['req'] = job_req
            job['location'] = job_location
            job['posted'] = job_posted

            # Update the jobs list with the updated dictionary
            if verbose: print('p2.job=', job)
            jobs2.append(job)

        jobs = jobs2            # overwrite the jobs list from the updated jobs2 list

    #########################################
    # 3rd phase is to save it to the database
    #########################################
    if verbose:
        print("**********************************")
        print("*** PHASE 3 - SAVE to database ***")
        print("**********************************")
    job_count = len(jobs)
    for job in jobs:

        job_title = str(job['title']).strip()
        job_req = str(job['req']).strip()
        job_location = str(job['location']).strip()
        job_posted = str(job['posted']).strip()
        job_url = str(job['url']).strip()

        if verbose:
            print("********* job ***********")
            print('p3.job=', job)

        if verbose:
            print("Title=", job_title)
            print("Req=", job_req)
            print("Location=", job_location)
            print("Date Posted=", job_posted)
            print("Job url=", job_url)
        else:
            print(job_title)            # at least show the titles

        save_job()

    ###################
    # CLEAN UP
    ###################
    print("...total jobs examined:", job_count)
    update_site()


def save_job():

    global errmsg
    global errors

    # If we don't have a job title value, then something went really wrong.  Skip this routine.
    if job_title == '':
            errmsg = "!!! ERROR - Job title value was missing.  Something really wrong!" \
                     " Site=" + site_description
            errors.append(errmsg)
            print(errmsg)
            err_dict['err_msg_friendly'] = errmsg
            err_dict['err_site'] = site_description
            err_dict['err_pattern'] = ''
            err_dict['err_url'] = ''
            err_dict['err_code'] = ''
            err_dict['err_msg_error'] = ''
            errors.append(err_dict)

            return

    # See if the job has already been logged.  Return if so.
    sql = "SELECT count(*) " \
          "FROM Jobs " \
          "WHERE Site_Id = " + str(site_id) + \
          " AND Job_Title = '" + job_title.replace("'", "''") + "' "           # Job title + [REQ | URL | Posted Date]

    if job_req != '':
        sql = sql + " AND Job_Req = '" + job_req + "'"   # First check by REQ
    else:
        if job_url != '':                                # if no REQ, go by job title + job URL
            sql = sql + " AND Job_URL='" + job_url + "'"
        else:                                          # if no req and no url, go by job title + job posting DATE
            sql = sql + " AND Job_Posted='" + job_posted + "'"

    if verbose: print("duplicate check sql =", sql)

    cursor.execute(sql)
    job_count = cursor.fetchone()
    #print("job count=", job_count)
    if job_count[0] > 0:

        print("...job already in database. Updating Job_Last_Detected...")

        sql = "UPDATE JOBS SET Job_Last_Detected='" + run_dt + "' " + sql[sql.find("WHERE"):]
        if verbose: print("update existing job sql =", sql)
        try:
            cursor.execute(sql)
            dbcon.commit()
        except Exception as e:
            errmsg = "!!! UPDATE ERROR - Could not update existing job"
            print(errmsg)
            err_dict['err_msg_friendly'] = errmsg
            err_dict['err_site'] = site_description
            err_dict['err_pattern'] = ''
            err_dict['err_url'] = job_url
            err_dict['err_code'] = sql
            err_dict['err_msg_error'] = str(e)
            errors.append(err_dict)

        return

    # Save the job to the database
    sql = "INSERT INTO Jobs ('Site_ID','Job_Title','Job_Posted','Job_Req','Job_Location','Job_URL'," \
        "'Job_Inserted','Job_Last_Detected') " \
        "VALUES (" \
        " " + str(site_id) + ", " \
        "'" + str(job_title).replace("'", "''") + "', " \
        "'" + str(job_posted) + "', "  \
        "'" + str(job_req) + "', " \
        "'" + str(job_location).replace("'", "''") + "', " \
        "'" + str(job_url) + "', " \
        "'" + str(run_dt) + "', " \
        "'" + str(run_dt) + "') "

    if verbose: print("INSERT job sql =", sql)
    try:
        cursor.execute(sql)
        dbcon.commit()
        print("...job saved to database.")
    except Exception as e:
        errmsg = "!!! INSERT ERROR - Could not insert new job"
        print(errmsg)
        err_dict['err_msg_friendly'] = errmsg
        err_dict['err_site'] = site_description
        err_dict['err_pattern'] = ''
        err_dict['err_url'] = job_url
        err_dict['err_code'] = sql
        err_dict['err_msg_error'] = str(e)
        errors.append(err_dict)

def update_site():

    global errmsg
    global errors

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
    print("...site updated")

def send_email():

    global errmsg
    global errors
    global hour

    sql = "select S.Site_Description, J.Job_Title, J.Job_Inserted, J.Job_Req, J.Job_Posted, J.Job_URL, " \
            "J.Job_Location, S.Site_URL "\
            "from Jobs J, Sites S " \
            "where J.Site_Id=S.Site_Id "

    # fake the hour for non-prod debugging
    #if prod != "true": hour = 4


    # Depends on the time.
    #   Before 5am - complete listing of everything still active
    #   5am to 8 pm - differential listings
    #   after 8pm - daily summary
    if int(hour) < 5:  # if before 5am, then list everything that is still active
        emailsubject = "JOB Postings Complete Listing as of " + run_dt
        sql += "AND Job_Last_Detected = '" + run_dt + "' "
    else:
        if int(hour) > 19:          # if after 8pm, then list everything found just today
            emailsubject = "JOB Postings Daily Digest for " + today
            sql += "AND Job_Inserted > '" + today + "' "
        else:  # between 5am and 8pm
            emailsubject = "JOB Postings Incremental for " + run_dt
            sql += "AND Job_Inserted = '" + run_dt + "' "
    # add the order by clause
    sql += "ORDER BY Site_Description; "

    if prod != "true":
        emailsubject = "DEV - " + emailsubject


    if verbose: print("Email Report SQL=", sql)
    cursor.execute(sql)
    jobs = cursor.fetchall()

    if len(jobs) == 0 and len(errors) == 0:
        print("No jobs/errors were found on this run.  Email cancelled.")
        return

    # start the HTML w/ header
    html = "<html><table width=100%><tr>" \
        "<td><b>Company</b</td>" \
        "<td><b>Job Title</b</td>" \
        "<td><b>Date Posted</b</td>" \
        "<td><b>Date Found</b</td>" \
        "</tr>"

    # will trigger the company row
    previous_company = ''

    for job in jobs:
        company = job[0]    # Capture all the values
        title = job[1]
        inserted = job[2][:16]
        req = job[3]
        posted = job[4]
        url = job[5]
        location = job[6]
        site_url = job[7]
        if url == '':                       # If the job url is missing, substitute the site url for the link
            url = site_url

        if company != previous_company:         # change in company, write out company header w/link
            html += "<tr width=100%><td><a href='" + site_url + "'>" + company + "</a></td></tr>"
            previous_company = company

        html += "<tr><td>&nbsp;</td>"
        html += "<td><a href='" + url + "'>" + title + "</a></td>"
        # html += "<td>" + req + "</td>"
        html += "<td>" + posted + "</td>"
        html += "<td>" + inserted + "</td>"
        # html += "<td>" + location + "</td>"
        html += "</tr>"
    html += "</table><hr>"

    # List out the errors
    if errors:
        html += "Error(s) detected:<table width='100%'>"
        for err in errors:
            html += "<tr width='100%'>"
            html += "<td>" + err['err_msg_friendly'] + "</td>"
            html += "<td><a href='" + err['err_url'] + "'>" + err['err_site'] + "</a></td>"
            html += "<td>" + err['err_pattern'] + "</td>"
            html += "<td>" + err['err_code'] + "</td>"
            html += "<td>" + err['err_msg_error'] + "</td>"
            html += "</tr>"
        html += "</table>"
    else:
        html += "No errors detected."

    # Finish the html
    html += "</html>"

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

    print("...email sent")

    # Logout of mailbox
    mailbox.logout()


def test_code():


    err_dic = {}

    #err_dict['err_inserted'] = "this is the timestamp"
    err_dic['err_msg_friendly'] = "this is a friendly message"
    err_dic['err_site'] = "this is the site name"
    err_dic['err_pattern'] = "this is the pattern name"
    err_dic['err_url'] = "this is the url in error"
    err_dic['err_code'] = "this is the custom code from the database"
    err_dic['err_msg_error'] = "this is the actual error message raised by the exception"
    errors.append(err_dic)



##########################################
# MAIN
##########################################

print("*********** START ***************")
#test_code()

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
    cursor = dbcon.cursor()
    print("Database connected")
except Exception as e:
    errmsg = "!!! FATAL ERROR Database NOT connected." \
             " Error=" + str(e)
    print(errmsg)
    quit()

# GET the environment variable  (PROD vs NONPROD)
prod = os.environ.get("PRODUCTION").lower()
if prod == "true":       # prod-settings
    verbose = False
    max_pages = 5
else:                   # non-prod settings
    max_pages = 3

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
    sql = "SELECT Site_ID, Site_URL, Site_Last_Scan_Date, Site_Times_Scanned_Today, Site_Description, " \
          "Site_Search, Site_Pattern_ID " \
          "FROM Sites " \
          "WHERE Site_Status='A' "

    #print(sql)

    try:
        cursor.execute(sql)
        sites = cursor.fetchall()
    except Exception as e:
        errmsg = "!!! INSERT ERROR - Could not retrieve a list of sites." \
                 " SQL=" + sql + \
                 " Error=" + str(e)
        print(errmsg)
        quit()

    for site in sites:
        site_id = site[0]                      #Capture all the values
        site_url = site[1]
        base_url = site_url[0:site_url.find("/", 8)]                     # grab the base URL
        site_last_scan_date = site[2]
        site_times_scanned_today = site[3]
        site_description = site[4]
        site_search = site[5]
        site_pattern_id = site[6]

        #TODO: if Site_Last_Scan_Date = today AND Site_Times_Scanned_Today > 10 THEN Continue (SKIP THIS ITERATION)

        scan_by_pattern()                # Should be the primary way

    # Close browser
    browser.close()

    # List out the errors
    if errors:
        print("********* ", len(errors), "Errors Found ***********")
        for err_dict in errors:
            print(err_dict)

            err_inserted = run_dt               # use the rund_dt
            err_msg_friendly = err_dict.get('err_msg_friendly', '')
            err_site = err_dict.get('err_site', '')
            err_pattern = err_dict.get('err_pattern', '')
            err_url = err_dict.get('err_url', '')
            err_code = err_dict.get('err_code', '')
            err_msg_error = err_dict.get('err_msg_error', '')

            sql = "INSERT INTO errors " \
                  "(err_inserted, err_msg_friendly, err_site, err_pattern, err_url, err_code, err_msg_error)" \
                  " VALUES (" + \
                  "'" + str(err_inserted) + "', " \
                  "'" + str(err_msg_friendly) + "', " \
                  "'" + str(err_site) + "', " \
                  "'" + str(err_pattern) + "', " \
                  "'" + str(err_url) + "', " \
                  "'" + str(err_code).replace("'", "''") + "', " \
                  "'" + str(err_msg_error).replace("'", "''") + "'" \
                  ");"
            # if verbose: print("save error sql=", sql)
            cursor.execute(sql)
            dbcon.commit()

            if verbose:
                print("save error to database:")
                print("  >> err_inserted =", err_msg_friendly)
                print("  >> err_msg_friendly =", err_msg_friendly)
                print("  >> err_site =", err_site)
                print("  >> err_pattern =", err_pattern)
                print("  >> err_url =", err_url)
                print("  >> err_code =", err_code)
                print("  >> err_msg_error =", err_msg_error)

            #sql = "INSERT INTO errors (error_inserted, error_description) VALUES (" \
            #    "'" + run_dt + "'," \
            #    "'" + err.replace("'", "''") + "')"             #Double up the single quotes in the error string
            #print("save error sql=", sql)
            #cursor.execute(sql)
            #dbcon.commit()
        print("********* END ERRORS LISTING ***************")
    else:
        print("...no errors logged.  Woo hoo!")

    # Send the report to INBOX
    send_email()

    # sleep for awhile if production, else quit after one loop
    if prod == "true":
        print("...sleeping...")
        time.sleep(14400)       # four hours
    else:
        print("*** Non-PROD exit ***")
        break                   # out of forever loop

quit()          # Don't go past here

##########################################################
# SAMPLE CODE, Parking Lot, Obsolete below; cannot be run
###########################################################

# soup.find('table', {'id': 'jobs_table'}).find_all('tr')       # works, but brings back heading row
# soup.find_all('tr', {'id': 'row_job'})                        # didn't work


# Selenium CSS Selector TIPS
#https://seleniumpythontutorial.wordpress.com/selenium-tips-css-selector/
#browser.find_element_by_css_selector("ul.srSearchOptionList li:nth-of-type(3)").click()  #click the 3rd menu item


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

