import oci
import logging
from fastapi import HTTPException
import os
from dotenv import load_dotenv
import redis
import json

load_dotenv()

COMPARTMENT_ID = os.getenv("COMPARTMENT_ID")
ENDPOINT = os.getenv("ENDPOINT")
MODEL_ID = os.getenv("MODEL_ID")

EXPIRE_TIME = int(os.getenv("EXPIRE_TIME", 86400)) #the time to expire the redis session in seconds
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", 20))
# Ensure the max message limit is an even number so conversational turns are kept in perfect Action/Reaction pairs.
if MAX_HISTORY_MESSAGES % 2 != 0:
    MAX_HISTORY_MESSAGES += 1

logger = logging.getLogger(__name__)

class LLMManager:
    def __init__(self, compartment_id: str, endpoint: str, model_id: str):
        self.compartment_id = compartment_id
        self.endpoint = endpoint
        self.model_id = model_id
        config_path = os.getenv("OCI_CONFIG_FILE", "config")
        self.config = oci.config.from_file(config_path, "DEFAULT") if os.path.exists(config_path) else {}

        self._client = None
        
        # Initialize Redis connection (adjust host/port if necessary)
        self.redis_client = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=int(os.getenv("REDIS_PORT", 6379)), db=0, decode_responses=True)
    
    @property
    def client(self):
        if self._client is None:
            try:
                genai_module = getattr(oci, 'generative_ai_inference', None)
                if genai_module is None:
                    raise AttributeError("generative_ai_inference module not found in OCI SDK")
                
                self._client = genai_module.GenerativeAiInferenceClient(
                    config=self.config,
                    service_endpoint=self.endpoint,
                    retry_strategy=oci.retry.NoneRetryStrategy(),
                    timeout=(10, 240)
                )
                logger.info("OCI Generative AI client initialized successfully")
            except Exception as e:
                logger.error(f"Generative AI module error: {str(e)}")
                raise HTTPException(status_code=500, detail=str(e))
        return self._client

    def llm_model(self, prompt: str, system_prompt: str = None, session_id: str = None, max_tokens: int = 600, temperature: float = 1.0, top_p: float = 1.0, top_k: int = 0, frequency_penalty: float = 0.0, presence_penalty: float = 0.0):
        try:
            logger.info(f"Generating chat response (prompt length: {len(prompt)})")
            genai_module = getattr(oci, 'generative_ai_inference')
            
            chat_detail = genai_module.models.ChatDetails()
            chat_request = genai_module.models.CohereChatRequest()
            chat_request.message = prompt
            if system_prompt:
                chat_request.preamble_override = system_prompt
                
            history_dicts = []
            if session_id:
                try:
                    raw_history = self.redis_client.get(f"chat_session:{session_id}")
                    if raw_history:
                        history_dicts = json.loads(raw_history)
                        cohere_history = []
                        # Reconstruct OCI Cohere objects from JSON dicts
                        for msg in history_dicts:
                            if msg.get('role') == 'USER':
                                cohere_history.append(genai_module.models.CohereUserMessage(message=msg['message']))
                            elif msg.get('role') == 'CHATBOT':
                                cohere_history.append(genai_module.models.CohereChatBotMessage(message=msg['message']))
                        chat_request.chat_history = cohere_history
                    else:
                        chat_request.chat_history = []
                except Exception as redis_err:
                    logger.warning(f"Redis connection failed when retrieving history for {session_id}. Proceeding without history. Error: {redis_err}")
                    chat_request.chat_history = []
            chat_request.max_tokens = max_tokens
            chat_request.temperature = temperature
            chat_request.frequency_penalty = frequency_penalty
            chat_request.presence_penalty = presence_penalty
            chat_request.top_p = top_p
            chat_request.top_k = top_k
            chat_request.safety_mode = "CONTEXTUAL"
            
            chat_detail.serving_mode = genai_module.models.OnDemandServingMode(model_id=self.model_id)
            chat_detail.chat_request = chat_request
            chat_detail.compartment_id = self.compartment_id
            
            chat_response = self.client.chat(chat_detail)
            
            if chat_response.data and chat_response.data.chat_response and chat_response.data.chat_response.text:
                response_text = chat_response.data.chat_response.text
                logger.info(f"Chat response generated successfully (length: {len(response_text)} characters)")
                
                if session_id:
                    # Append new messages to the dictionary list
                    history_dicts.append({"role": "USER", "message": prompt})
                    history_dicts.append({"role": "CHATBOT", "message": response_text})
                    
                    # Enforce maximum history limit to save tokens and improve performance
                    if len(history_dicts) > MAX_HISTORY_MESSAGES:
                        logger.info(f"Truncating session memory to the last {MAX_HISTORY_MESSAGES} messages.")
                        history_dicts = history_dicts[-MAX_HISTORY_MESSAGES:]
                        
                    # Save back to Redis, setting it to expire after 24 hours (86400 seconds)
                    try:
                        self.redis_client.setex(f"chat_session:{session_id}", EXPIRE_TIME, json.dumps(history_dicts))
                    except Exception as redis_err:
                        logger.warning(f"Redis connection failed when saving history for {session_id}. Error: {redis_err}")
                    
                return response_text
            else:
                raise HTTPException(status_code=500, detail="No response content from AI model")
        except oci.exceptions.ServiceError as e:
            logger.error(f"OCI Service Error: {str(e)}", exc_info=True)
            raise HTTPException(status_code=e.status, detail=f"OCI Service Error: {str(e)}")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error generating chat response: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    def clear_history(self, session_id: str):
        try:
            result = self.redis_client.delete(f"chat_session:{session_id}")
            if result > 0:
                logger.info(f"Cleared chat history for session: {session_id}")
                return True
            return False
        except Exception as redis_err:
            logger.warning(f"Redis connection failed when clearing history for {session_id}. Error: {redis_err}")
            return False

    def embed_text(self, inputs, model_id: str = "cohere.embed-v4.0", truncate: str = "NONE"):
        try:
            if isinstance(inputs, str):
                inputs = [inputs]
            logger.info(f"Generating embeddings for {len(inputs)} inputs")
            genai_module = getattr(oci, 'generative_ai_inference')
            
            embed_text_detail = genai_module.models.EmbedTextDetails()
            embed_text_detail.serving_mode = genai_module.models.OnDemandServingMode(model_id=model_id)
            embed_text_detail.inputs = inputs
            embed_text_detail.truncate = truncate
            embed_text_detail.compartment_id = self.compartment_id
            
            embed_text_response = self.client.embed_text(embed_text_detail)
            
            logger.info("Embeddings generated successfully")
            return embed_text_response.data
        except oci.exceptions.ServiceError as e:
            logger.error(f"OCI Service Error: {str(e)}", exc_info=True)
            raise HTTPException(status_code=e.status, detail=f"OCI Service Error: {str(e)}")
        except Exception as e:
            logger.error(f"Error generating embeddings: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

llm_manager = LLMManager(
    compartment_id=COMPARTMENT_ID,
    endpoint=ENDPOINT,
    model_id=MODEL_ID
)
