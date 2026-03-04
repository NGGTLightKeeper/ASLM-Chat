import sys, os
sys.path.insert(0, os.path.join(os.getcwd()))

from django.shortcuts import render
from django.views.generic import TemplateView, DetailView, ListView
from ..Data.models import *

# Main Page
class main(TemplateView):
    template_name = 'main/main.html'

# Profile Page
class profile(TemplateView):
    template_name = 'main/profile.html'
