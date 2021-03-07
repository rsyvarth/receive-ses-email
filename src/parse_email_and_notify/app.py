import os
import json
import boto3
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

s3 = boto3.resource('s3')
sns_client = boto3.client('sns', region_name=os.environ['AWS_REGION'])
ses_client = boto3.client('ses', region_name=os.environ['AWS_REGION'])

def lambda_handler(event, context):

  bucket_key = event['Records'][0]['s3']['object']['key']
  bucket_name = event['Records'][0]['s3']['bucket']['name']
  bucket_region = event['Records'][0]['awsRegion']

  obj_content_string = get_file(bucket_key, bucket_name, bucket_region)

  link_to_file = "https://s3.console.aws.amazon.com/s3/object/" + bucket_name + "?region=" + bucket_region + "&prefix=" + bucket_key

  content_type, email = parse_email_obj(obj_content_string, link_to_file)

  try:
    send_notification_email(content_type, email)
    return True
  except Exception as error:
    # If we fail to send the message, log the error and try to email the exception instead
    print(error)
    email = get_notification_template("failed send", f"Failed to send email: {error}", link_to_file)
    send_notification_email("failed send", email)


def get_file(bucket_key, bucket_name, bucket_region):

  obj = s3.Object(bucket_name, bucket_key)
  obj_content_string = obj.get()['Body'].read().decode('utf-8')

  return obj_content_string

def parse_email_obj(obj_content_string, link_to_file):
  email = email.message_from_string(obj_content_string)

  if "Delivery Status Notification (Failure)" in obj_content_string:
    content_type = "delivery failure (bad email)"
    initial_string = obj_content_string.split("An error occurred while trying to deliver the mail to the following recipients:",1)[1]
    notification_message = f"Delivery error sending to: {initial_string.split('------=_Part_')[0].strip()}"
    email = get_notification_template(content_type, notification_message, link_to_file)

  elif "Delivery error report" in obj_content_string:
    content_type = "delivery error (bot)"
    initial_string = obj_content_string.split("envelope-from=",1)[1]
    notification_message = f"Sender: {initial_string.split(';')[0].strip()}"
    email = get_notification_template(content_type, notification_message, link_to_file)

  else:
    content_type = "inbound message"
    # Leave the email untouched when we get an inbound message

  return content_type, email

def get_notification_template(content_type, notification_message, link_to_file):

  # To run unit tests for this function, we need to specify an absolute file path
  abs_dir = os.path.dirname(os.path.abspath(__file__))
  with open(os.path.join(abs_dir, 'notification_email_template.html')) as fh:
      contents = fh.read()

  notification_email_contents = contents.replace("{content_type}", content_type)
  notification_email_contents = notification_email_contents.replace("{notification_message}", notification_message)
  notification_email_contents = notification_email_contents.replace("{link_to_file}", link_to_file)

  # Create a MIME container.
  msg = MIMEMultipart()
  # Attach the text part to the MIME message.
  msg.attach(MIMEText(notification_email_contents, _subtype="html"))

  msg['Subject'] = "Email received - " + content_type

  return msg

def send_notification_email(content_type, message):

    # Remove incorrect headers for our forwarding
    del message['Received']
    del message['Return-Path']

    # Replace message To with our address
    message.replace_header('To', os.environ['EMAIL_ADDRESS'])

    # Set the "Reply-To" to our original "From" so when we reply to the message
    # it goes to the original sender, not emailreceived@...
    message['Reply-To'] = message['From']
    message.replace_header('From', "Email received notification <emailreceived@" + os.environ['EMAIL_DOMAIN'] + ">")

    response = ses_client.send_raw_email(
        RawMessage={
            'Data': message.as_bytes()
        }
    )

    return response
