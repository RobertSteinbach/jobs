FROM python:3
ADD main.py /
ADD geckodriver /
# ADD ./db/jobs.db /db/jobs.db
RUN pip3 install beautifulsoup4==4.9.3
RUN pip3 install selenium==3.141.0
CMD [ "python3","./main.py" ]
# ENV IMAP_SERVER=mail.server.com
# ENV IMAP_LOGIN=email@address.com
# ENV IMAP_PWD=email_password
# ENV EMAIL_ADDRESS=my_email@address.com
# ENV PRODUCTION=true