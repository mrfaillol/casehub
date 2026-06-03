"""
VPS Monitor Collectors
"""
from .system import SystemCollector
from .pm2 import PM2Collector
from .services import ServicesCollector
from .applications import ApplicationsCollector
from .whatsapp import WhatsAppCollector
from .integrations import IntegrationsCollector
from .database import DatabaseCollector
from .nginx import NginxCollector

__all__ = ['SystemCollector', 'PM2Collector', 'ServicesCollector', 'ApplicationsCollector', 'WhatsAppCollector', 'IntegrationsCollector', 'DatabaseCollector', 'NginxCollector']
