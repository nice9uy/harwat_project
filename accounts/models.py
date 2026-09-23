from django.db import models


class RevokedToken(models.Model):
    jti = models.CharField(max_length=255, unique=True, db_index=True)
    revoked_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
