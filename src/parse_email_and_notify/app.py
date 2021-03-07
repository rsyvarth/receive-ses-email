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
    return "Message send success."
  except Exception as error:
    return f"Message send failed, error: {error}"

def get_file(bucket_key, bucket_name, bucket_region):

  obj = s3.Object(bucket_name, bucket_key)
  obj_content_string = obj.get()['Body'].read().decode('utf-8')

  return obj_content_string

def parse_email_obj(obj_content_string, link_to_file):

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
    email = get_email_contents(obj_content_string)

  return content_type, email

def get_email_contents(obj_content_string):

  message = email.message_from_string(obj_content_string)

  return message

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

    # Replace message To with our address
    del message['To']
    message['To'] = os.environ['EMAIL_ADDRESS']

    if 'From' not in message:
        message['From'] = "Email received notification <emailreceived@" + os.environ['EMAIL_DOMAIN'] + ">",

    response = ses_client.send_raw_email(
        Source = message['From'],
        Destination = {
            "ToAddresses": [
                message['To']
            ]
        },
        RawMessage={
            'Data': message.to_string()
        }
    )

    return response
