from django.db import models
from django.contrib.auth.models import User


class ChatMessage(models.Model):
    """Store chat messages per user account for persistent chat history."""
    
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_messages')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    symbol = models.CharField(max_length=50, blank=True, null=True, help_text="Trading symbol if chart context was provided")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['user', 'symbol']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.role}: {self.content[:50]}..."
