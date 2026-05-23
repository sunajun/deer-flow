from deerflow.governance.models import PermissionRule, Role, RoleType

BUILTIN_ROLES: dict[RoleType, Role] = {
    RoleType.ADMIN: Role(
        role_type=RoleType.ADMIN,
        name="管理员",
        description="完全控制权限",
        permissions=PermissionRule(
            allowed_scenes=["*"],
            allowed_tools=["*"],
            max_parallel_sessions=10,
            can_create_agents=True,
            can_manage_skills=True,
            can_schedule_tasks=True,
        ),
    ),
    RoleType.USER: Role(
        role_type=RoleType.USER,
        name="普通用户",
        description="日常使用权限",
        permissions=PermissionRule(
            allowed_scenes=["conversation", "planning", "file_operation"],
            allowed_tools=["*", "!agent_manage", "!skill_manage"],
            max_parallel_sessions=3,
            can_create_agents=False,
            can_manage_skills=False,
            can_schedule_tasks=True,
        ),
    ),
    RoleType.GUEST: Role(
        role_type=RoleType.GUEST,
        name="访客",
        description="只读对话权限",
        permissions=PermissionRule(
            allowed_scenes=["conversation"],
            allowed_tools=["chat", "clarify"],
            max_parallel_sessions=1,
            can_create_agents=False,
            can_manage_skills=False,
            can_schedule_tasks=False,
        ),
    ),
}
