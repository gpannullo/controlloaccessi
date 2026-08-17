def has_role(user, role_name):
    return user.groups.filter(name=role_name).exists()