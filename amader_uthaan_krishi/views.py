from django.shortcuts import render

from apps.products.models import Product

def home(request):

    products = Product.objects.all().order_by('?')[:8]

    return render(request, 'index.html', {
        'products': products
    })
from django.shortcuts import render

def contact(request):
    return render(request, 'contact.html')

def about(request):
    return render(request, 'about.html')