def notifications(request):
    u = request.user
    return {"nb_notifs": u.notifications.filter(lu=False).count() if u.is_authenticated else 0}
