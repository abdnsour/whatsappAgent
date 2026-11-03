import os
from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()

account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
to_number = os.getenv("WHATSAPP_TO_NUMBER")

if not account_sid or not auth_token:
    raise ValueError("Missing TWILIO_ACCOUNT_SID or TWILIO_AUTH_TOKEN in environment variables.")

client = Client(account_sid, auth_token)

message = client.messages.create(
    from_='whatsapp:+14155238886',
    body='hello',
    to=to_number or 'whatsapp:+1234567890'
)

print(message.sid)