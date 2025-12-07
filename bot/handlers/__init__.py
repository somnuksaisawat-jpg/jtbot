from aiogram import Router
from .menu import router as menu_router
from .personal import router as personal_router
from .monitor import router as monitor_router
from .notify import router as notify_router
from .payment import router as payment_router
# 🟢 确保这两行存在
from .autodm import router as autodm_router 
from .support import router as support_router 

router = Router()

# 注册顺序
router.include_router(monitor_router)
router.include_router(personal_router)
router.include_router(notify_router)
router.include_router(payment_router)
# 🟢 确保这两行被 include 了
router.include_router(autodm_router)
router.include_router(support_router)

# menu 必须放最后
router.include_router(menu_router)