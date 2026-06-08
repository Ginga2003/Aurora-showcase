from django import forms
from .models import User
from django.contrib.auth.models import User as AuthUser
from django.core.exceptions import ValidationError
import re

class UserRegistrationForm(forms.ModelForm):
    # Additional fields not directly in the model or requiring special handling
    password = forms.CharField(widget=forms.PasswordInput(attrs={'id': 'pwd1'}), label='Password')
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={'id': 'pwd2'}), label='Confirm Password')
    
    # We will accept a Base64 string from the frontend Cropper.js
    avatar_base64 = forms.CharField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model = User
        fields = ['username', 'email']
        widgets = {
            'username': forms.TextInput(attrs={'id': 'uname'}),
            'email': forms.EmailInput(attrs={'id': 'email'}),
        }

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists() or AuthUser.objects.filter(username=username).exists():
            raise ValidationError("This username is already taken.")
        return username

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', "Passwords do not match.")
            
        return cleaned_data


class UserProfileUpdateForm(forms.ModelForm):
    # Similar to registration, but passwords are optional and username cannot be changed if it clashes with others
    new_password = forms.CharField(widget=forms.PasswordInput(attrs={'id': 'pwd1'}), required=False, label='New Password')
    confirm_new_password = forms.CharField(widget=forms.PasswordInput(attrs={'id': 'pwd2'}), required=False, label='Confirm New Password')
    avatar_base64 = forms.CharField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model = User
        fields = ['username', 'phone_number', 'email', 'city', 'birth']
        widgets = {
            'username': forms.TextInput(attrs={'id': 'uname'}),
            'phone_number': forms.TextInput(attrs={'id': 'phone'}),
            'email': forms.EmailInput(attrs={'id': 'email'}),
            'city': forms.TextInput(attrs={'id': 'city'}),
            'birth': forms.DateInput(attrs={'type': 'date', 'id': 'birth'}),
        }

    def clean_username(self):
        username = self.cleaned_data.get('username')
        # Check if username exists and it's NOT the current user's username
        if User.objects.filter(username=username).exclude(pk=self.instance.pk).exists() or \
           AuthUser.objects.filter(username=username).exclude(username=self.instance.username).exists():
            raise ValidationError("This username is already taken.")
        return username

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("new_password")
        confirm_password = cleaned_data.get("confirm_new_password")

        if password or confirm_password:
            if password != confirm_password:
                self.add_error('confirm_new_password', "New passwords do not match.")
                
        return cleaned_data
