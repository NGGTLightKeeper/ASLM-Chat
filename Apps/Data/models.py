from django.db import models
import uuid

class Chat(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, default="New Chat")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']
        
    def __str__(self):
        return self.title

class Message(models.Model):
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=50) # 'user', 'assistant', 'system'
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']
        
    def __str__(self):
        return f"{self.role}: {self.content[:50]}"


class MessageImage(models.Model):
    """Stores images attached to a user message (base64, no file system needed)."""
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='images')
    mime_type = models.CharField(max_length=50, default='image/jpeg')
    data = models.TextField()  # base64-encoded image data (without data: prefix)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def data_url(self):
        return f"data:{self.mime_type};base64,{self.data}"

    def __str__(self):
        return f"Image #{self.order} for message {self.message_id}"
