from .models import User as CustomUser

def player_context(request):
    """
    Injects the user profile into the template context.
    """
    context = {'user_profile': None}
    
    if request.user.is_authenticated:
        try:
            custom_user = CustomUser.objects.get(username=request.user.username)
            context['user_profile'] = custom_user
        except CustomUser.DoesNotExist:
            pass
            
    return context
