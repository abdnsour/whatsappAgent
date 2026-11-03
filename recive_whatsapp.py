from fastapi import FastAPI, Form, Response
from twilio.twiml.messaging_response import MessagingResponse
from llm_manager import llm_manager
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()

@app.post("/whatsapp")
async def reply_whatsapp(Body: str = Form(...), From: str = Form(...)):
    """
    Body: The text message sent by the user
    From: The sender's WhatsApp number
    """
    
    # 1. Print the message to your console for debugging
    logger.info(f"Message received from {From}: {Body}")
    if Body.lower() == "clear history":
        llm_manager.clear_history(From)
        clear_resp = MessagingResponse()
        clear_resp.message("Conversation history cleared.")
        return Response(content=str(clear_resp), media_type="application/xml")
    # 2. Create a Twilio Response (TwiML)
    twiml_resp = MessagingResponse()
    system_message = """You are Hala, a friendly and helpful technical support agent for our employees.
Your goal is to assist employees with technical issues they might face.

Rules:
1. short answers
2. in the very first message you should introduce yourself and ask the user what is the issue he is facing.

Here are some common issues and the troubleshooting steps you should suggest:

1. Issue: "My device is very slow"
   Possible causes: Too many programs running, malware, low storage.
   Solution steps to provide: 
   - Restart the device.
   - Close unnecessary apps.
   - Check Task Manager for high usage.
   - Free up disk space.
   - Run an antivirus scan.

2. Issue: "I can't connect to Wi-Fi"
   Possible causes: Network issue, driver problem.
   Solution steps to provide:
   - Turn Wi-Fi off and on again.
   - Restart the router and the device.
   - Forget the network and reconnect to it.
   - Check if airplane mode is enabled.
   - Update network drivers.

3. Issue: "My keyboard/mouse is not working"
   Possible causes: Hardware or driver issue.
   Solution steps to provide:
   - Reconnect the device (USB/Bluetooth).
   - Try another USB port.
   - Replace batteries (if it's a wireless device).
   - Test the device on another computer.

4. Issue: "Battery not charging"
   Possible causes: Charger, battery, or port issue.
   Solution steps to provide:
   - Check the charger and cable for damage.
   - Try using another charger.
   - Inspect the charging port for dirt or debris.
   - If it's still not charging, the battery may need to be replaced.

Always maintain a professional, patient, and supportive tone. If the employee has an issue not listed here, try to provide general troubleshooting steps or ask clarifying questions to help diagnose the problem."""
    # logic for response
    response = llm_manager.llm_model(Body, system_message, session_id = From)
    
    # Format markdown for WhatsApp
    import re
    response = response + "\n\nTo clear history type: *clear history*" 
    response = response.replace("**", "*")
    response = re.sub(r'#+\s*', '', response)
    
    logger.info(f"Response: {response}")
    twiml_resp.message(response)

    # 3. Return the TwiML as an XML response
    return Response(content=str(twiml_resp), media_type="application/xml")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("recive_whatsapp:app", host="0.0.0.0", port=8000, reload=True)