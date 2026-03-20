import os
import logging
from typing import Optional

try:
    from linebot.v3.messaging import (
        Configuration,
        ApiClient,
        MessagingApi,
        PushMessageRequest,
        TextMessage
    )
    LINE_SDK_AVAILABLE = True
except ImportError:
    LINE_SDK_AVAILABLE = False

logger = logging.getLogger(__name__)

class LineNotifier:
    """
    A class to send notifications via LINE Messaging API (v3).
    """
    def __init__(self, access_token: Optional[str] = None, user_id: Optional[str] = None):
        """
        Initialize the LineNotifier.
        
        Args:
            access_token (str, optional): LINE Channel Access Token. Defaults to env LINE_CHANNEL_ACCESS_TOKEN.
            user_id (str, optional): LINE User ID to send message to. Defaults to env LINE_USER_ID.
        """
        self.access_token = access_token or os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
        self.user_id = user_id or os.environ.get('LINE_USER_ID')

    def send_summary(self, message: str) -> bool:
        """
        Send a text summary to the configured LINE User ID.
        
        Args:
            message (str): The text message to send.
            
        Returns:
            bool: True if sent successfully, False otherwise.
        """
        if not LINE_SDK_AVAILABLE:
            logger.warning("line-bot-sdk not installed. Cannot send LINE notification.")
            return False

        if not self.access_token or not self.user_id:
            logger.warning("LINE_CHANNEL_ACCESS_TOKEN or LINE_USER_ID not set. Skipping notification.")
            return False
            
        if not message:
            logger.warning("Empty message provided to LineNotifier.send_summary.")
            return False

        configuration = Configuration(access_token=self.access_token)
        
        try:
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                text_message = TextMessage(text=message)
                push_message_request = PushMessageRequest(
                    to=self.user_id,
                    messages=[text_message]
                )
                line_bot_api.push_message(push_message_request)
                logger.info("LINE notification sent successfully.")
                return True
        except Exception as e:
            logger.error(f"Failed to send LINE notification: {e}")
            return False
