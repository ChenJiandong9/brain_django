from django.db import models

class BrainData(models.Model):
    time = models.DateTimeField()  # 假设 time 是时间戳，使用 DateTimeField
    name = models.CharField(max_length=255)  # varchar(255)
    signal_quality = models.IntegerField()
    attention = models.IntegerField()
    meditation = models.IntegerField()
    delta = models.IntegerField()
    theta = models.IntegerField()
    low_alpha = models.IntegerField()
    low_gamma = models.IntegerField()
    low_beta = models.IntegerField()
    high_alpha = models.IntegerField()
    high_gamma = models.IntegerField()
    high_beta = models.IntegerField()

    def __str__(self):
        return f"{self.name} - {self.time}"