from django.db import models

class EEGRecord(models.Model):
    """
    脑电有效信息记录
    """
    recording_id = models.CharField(max_length=255,unique=True,verbose_name='记录ID')
    start_time = models.DateTimeField(verbose_name='开始时间')
    end_time = models.DateTimeField(verbose_name='结束时间')
    name=models.CharField(max_length=255,default='EEG_Recording',verbose_name='记录名称')
    description = models.TextField(verbose_name='描述')
    data_count= models.BigIntegerField(default=0,verbose_name='数据点数量')
    def __str__(self):
        return f"{self.name}({self.start_time}-{self.end_time})"
    class Meta:
        db_table='eeg_record'
        verbose_name='脑电有效记录'
        verbose_name_plural=verbose_name
        ordering=['-start_time']



class EEGDataPoint(models.Model):
    """
    脑电有效数据点
    """
    recording =models.ForeignKey(EEGRecord,on_delete=models.CASCADE,related_name='data_points')
    time=models.DateTimeField(verbose_name='时间')
    delta=models.IntegerField(default=0,verbose_name='Delta波')
    theta=models.IntegerField(default=0,verbose_name='Theta波')
    low_alpha=models.IntegerField(default=0,verbose_name='低Alpha波')
    low_beta=models.IntegerField(default=0,verbose_name='Low Beta波')
    low_gamma=models.IntegerField(default=0,verbose_name='Low Gamma波')
    high_alpha=models.IntegerField(default=0,verbose_name='High Alpha波')
    high_beta=models.IntegerField(default=0,verbose_name='High Beta波')
    high_gamma=models.IntegerField(default=0,verbose_name='High Gamma波')
    attention=models.IntegerField(default=0,verbose_name='注意力')
    meditation=models.IntegerField(default=0,verbose_name='冥想')
    signal_quality=models.IntegerField(default=0,verbose_name='信号质量')
    class Meta:
        db_table='eeg_data_point'
        verbose_name='脑电有效数据点'
        verbose_name_plural=verbose_name
        ordering=['time']
