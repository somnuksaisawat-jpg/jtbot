from aiogram.fsm.state import State, StatesGroup

class ProfileStates(StatesGroup):
    waiting_for_cdk = State()

class MonitorStates(StatesGroup):
    waiting_for_keyword = State()
    waiting_for_filter_word = State() # <--- [新增] 等待输入过滤词
    waiting_for_target_user = State()
    # ... (保留原有的 ProfileStates, MonitorStates)

class DMStates(StatesGroup):
    # 绑定群组
    waiting_for_feedback_group = State()
    
    # 账号管理
    adding_account_phone = State()
    adding_account_code = State()
    adding_account_password = State()
    
    # 内容编辑
    editing_content = State()
    editing_auto_reply = State()