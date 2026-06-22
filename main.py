"""
SKALPMAT V7 — Android App (KivyMD)
Запуск на Android через Buildozer
"""
import os
import sys
import threading
import queue
import time
from datetime import datetime
from pathlib import Path

# KivyMD imports
from kivy import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.properties import StringProperty, NumericProperty, BooleanProperty
from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.screenmanager import MDScreenManager
from kivymd.uix.toolbar import MDTopAppBar
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.list import MDList, OneLineAvatarIconListItem, IconLeftWidget
from kivymd.uix.dialog import MDDialog
from kivymd.uix.textfield import MDTextField
from kivymd.uix.spinner import MDSpinner
from kivymd.uix.snackbar import Snackbar
from kivymd.material_styles import MaterialStyle

# Android Foreground Service
from jnius import autoclass, cast

# Импортируем основную логику бота
from synergy_bot_v7 import (
    SynergyBot, TelegramCommands, load_config, init_database, 
    ensure_env_exists, get_open_trades, get_db_connection
)

# ==================== ANDROID FOREGROUND SERVICE ====================
class AndroidBackgroundService:
    """Управление фоновой службой Android для работы при заблокированном экране"""
    
    def __init__(self):
        self.service_running = False
        self.notification_id = 12345
        
        # Android классы
        try:
            self.Context = autoclass('android.content.Context')
            self.Intent = autoclass('android.content.Intent')
            self.PendingIntent = autoclass('android.app.PendingIntent')
            self.NotificationChannel = autoclass('android.app.NotificationChannel')
            self.NotificationManager = autoclass('android.app.NotificationManager')
            self.NotificationCompat = autoclass('androidx.core.app.NotificationCompat')
            self.Build = autoclass('android.os.Build')
            self.String = autoclass('java.lang.String')
            
            # Получаем контекст приложения
            from jnius import PythonJavaClass, java_method
            # Активность Kivy
            self.PythonActivity = autoclass('org.kivy.android.PythonActivity')
            self.mActivity = self.PythonActivity.mActivity
            self.context = cast(self.Context, self.mActivity)
            
            print("✅ Android service классы инициализированы")
        except Exception as e:
            print(f"⚠️ Android service не доступен (возможно на десктопе): {e}")
            self.Context = None
    
    def create_notification_channel(self):
        """Создать канал уведомлений для Android 8+"""
        if self.Context is None:
            return
        
        try:
            channel_id = "skalpmat_service_channel"
            channel_name = "SKALPMAT Trading Service"
            importance = self.NotificationManager.IMPORTANCE_LOW
            
            channel = self.NotificationChannel(channel_id, channel_name, importance)
            channel.setDescription("Торговый бот SKALPMAT работает в фоне")
            channel.setShowBadge(False)
            
            notification_manager = self.context.getSystemService(self.Context.NOTIFICATION_SERVICE)
            notification_manager.createNotificationChannel(channel)
            print("✅ Канал уведомлений создан")
        except Exception as e:
            print(f"⚠️ Ошибка создания канала: {e}")
    
    def start_service(self):
        """Запустить фоновую службу"""
        if self.Context is None:
            print("ℹ️ Android service не доступен (десктоп режим)")
            self.service_running = True
            return True
        
        try:
            # Создать канал уведомлений
            self.create_notification_channel()
            
            # Intent для службы
            service_intent = self.Intent(self.context, self.context.getClass())
            service_intent.setAction("START_SERVICE")
            
            # PendingIntent для клика по уведомлению
            pending_intent = self.PendingIntent.getActivity(
                self.context,
                0,
                self.Intent(self.context, self.PythonActivity),
                self.PendingIntent.FLAG_UPDATE_CURRENT | self.PendingIntent.FLAG_IMMUTABLE
            )
            
            # Построить уведомление
            builder = self.NotificationCompat.Builder(self.context, "skalpmat_service_channel")
            builder.setContentTitle("SKALPMAT V7")
            builder.setContentText("🟢 Бот торгует...")
            builder.setSmallIcon(self.context.getResources().getIdentifier('icon', 'drawable', self.context.getPackageName()))
            builder.setContentIntent(pending_intent)
            builder.setOngoing(True)  # Не свайпается
            builder.setPriority(self.NotificationCompat.PRIORITY_LOW)
            
            # Запустить службу
            notification = builder.build()
            self.PythonActivity.startForegroundService(service_intent)
            
            # Для Kivy/Python service нужно использовать NotificationManager
            notification_manager = self.context.getSystemService(self.Context.NOTIFICATION_SERVICE)
            notification_manager.notify(self.notification_id, notification)
            
            self.service_running = True
            print("✅ Фоновая служба запущена")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка запуска службы: {e}")
            # Fallback: просто ставим флаг
            self.service_running = True
            return True
    
    def update_notification(self, text, pnl=None):
        """Обновить уведомление в статус баре"""
        if self.Context is None or not self.service_running:
            return
        
        try:
            # PendingIntent для клика
            pending_intent = self.PendingIntent.getActivity(
                self.context,
                0,
                self.Intent(self.context, self.PythonActivity),
                self.PendingIntent.FLAG_UPDATE_CURRENT | self.PendingIntent.FLAG_IMMUTABLE
            )
            
            # Построить обновление
            builder = self.NotificationCompat.Builder(self.context, "skalpmat_service_channel")
            builder.setContentTitle("SKALPMAT V7")
            builder.setContentText(text)
            builder.setSmallIcon(self.context.getResources().getIdentifier('icon', 'drawable', self.context.getPackageName()))
            builder.setContentIntent(pending_intent)
            builder.setOngoing(True)
            
            if pnl is not None:
                if pnl >= 0:
                    builder.setSubText(f"🟢 +{pnl:.2f} USDT")
                else:
                    builder.setSubText(f"🔴 {pnl:.2f} USDT")
            
            notification = builder.build()
            notification_manager = self.context.getSystemService(self.Context.NOTIFICATION_SERVICE)
            notification_manager.notify(self.notification_id, notification)
            
        except Exception as e:
            print(f"⚠️ Ошибка обновления уведомления: {e}")
    
    def stop_service(self):
        """Остановить фоновую службу"""
        if self.Context is None:
            self.service_running = False
            return
        
        try:
            service_intent = self.Intent(self.context, self.context.getClass())
            service_intent.setAction("STOP_SERVICE")
            self.context.stopService(service_intent)
            
            # Удалить уведомление
            notification_manager = self.context.getSystemService(self.Context.NOTIFICATION_SERVICE)
            notification_manager.cancel(self.notification_id)
            
            self.service_running = False
            print("✅ Фоновая служба остановлена")
        except Exception as e:
            print(f"⚠️ Ошибка остановки службы: {e}")
            self.service_running = False

# ==================== ГЛАВНЫЙ ЭКРАН ====================
class MainScreen(MDScreen):
    log_text = StringProperty("")
    status_text = StringProperty("⏸️ Готов к работе")
    positions_text = StringProperty("📊 Нет открытых позиций")
    is_running = BooleanProperty(False)
    pnl_text = StringProperty("PnL: 0.00 USDT")
    balance_text = StringProperty("Баланс: -- USDT")
    background_service_enabled = BooleanProperty(False)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bot = None
        self.tg_commands = None
        self.msg_queue = queue.Queue()
        self._carousel_running = False
        self._carousel_index = 0
        self._carousel_positions = []
        self.bg_service = AndroidBackgroundService()  # ✅ Фоновая служба
        
    def append_log(self, text):
        """Добавить сообщение в лог"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {text}"
        if self.log_text:
            self.log_text += line + "\n"
        else:
            self.log_text = line + "\n"
        
        # Ограничиваем лог последними 500 строками
        lines = self.log_text.split("\n")
        if len(lines) > 500:
            self.log_text = "\n".join(lines[-500:])
    
    def update_status(self, text):
        """Обновить статус бар"""
        self.status_text = f"🔍 {text}"
    
    def update_positions_carousel(self, text):
        """Обновить карусель позиций"""
        self.positions_text = text
    
    def update_pnl(self, pnl, balance=None):
        """Обновить PnL и баланс"""
        sign = "+" if pnl >= 0 else ""
        color = "[color=00ff00]" if pnl >= 0 else "[color=ff0000]"
        self.pnl_text = f"{color}PnL: {sign}{pnl:.2f} USDT[/color]"
        
        if balance:
            self.balance_text = f"💵 Баланс: {balance:.2f} USDT"
        
        # ✅ Обновить фоновое уведомление
        if self.background_service_enabled and self.bg_service.service_running:
            self.bg_service.update_notification(
                f"{self.positions_text} | {self.status_text}",
                pnl
            )
    
    def start_bot_thread(self):
        """Запустить бота в отдельном потоке"""
        def run_bot():
            try:
                self.append_log("🚀 Запуск skalpMat...")
                self.bot = SynergyBot(self.append_log, self.update_status)
                self.tg_commands = TelegramCommands(self.bot)
                self.tg_commands.start_polling()
                self.bot.start()
                
                # ✅ Запустить фоновую службу если включена
                if self.background_service_enabled:
                    self.bg_service.start_service()
                    self.append_log("✅ Фоновая служба запущена")
                
                Clock.schedule_once(lambda dt: self.set_running(True), 0.5)
                self._start_positions_carousel()
            except Exception as e:
                self.append_log(f"❌ Ошибка запуска: {e}")
                Clock.schedule_once(lambda dt: Snackbar(text=f"Ошибка: {e}").open(), 0)
        
        thread = threading.Thread(target=run_bot, daemon=True)
        thread.start()
    
    def stop_bot_thread(self):
        """Остановить бота"""
        if self.bot:
            self.append_log("⏳ Остановка бота...")
            self.bot.stop()
            self._stop_positions_carousel()
            
            # ✅ Остановить фоновую службу
            if self.background_service_enabled:
                self.bg_service.stop_service()
                self.append_log("✅ Фоновая служба остановлена")
            
            self.set_running(False)
    
    def set_running(self, is_running):
        """Обновить состояние UI"""
        self.is_running = is_running
    
    def toggle_bot(self):
        """Старт/Стоп бота"""
        if self.is_running:
            self.stop_bot_thread()
        else:
            self.start_bot_thread()
    
    def show_positions(self):
        """Показать открытые позиции"""
        if not self.bot:
            Snackbar(text="⚠️ Бот не запущен").open()
            return
        
        status = self.bot.get_open_positions_status()
        self.append_log(f"\n{status}")
    
    def show_stats(self):
        """Показать статистику"""
        if not self.bot:
            Snackbar(text="⚠️ Бот не запущен").open()
            return
        
        stats = self.bot.get_stats_text()
        self.append_log(f"\n{'='*50}\n{stats}\n{'='*50}")
    
    def show_report(self):
        """Показать отчёт"""
        if not self.bot:
            Snackbar(text="⚠️ Бот не запущен").open()
            return
        
        report = self.bot.get_report()
        self.append_log(f"\n{report}")
    
    def close_all_positions(self):
        """Закрыть все позиции"""
        if not self.bot:
            Snackbar(text="⚠️ Бот не запущен").open()
            return
        
        result = self.bot.close_all_positions()
        self.append_log(f"\n{result}")
        Snackbar(text=result).open()
    
    def run_backtest(self):
        """Запустить бэктест"""
        if not self.bot or not self.bot.gate:
            Snackbar(text="⚠️ Бот не запущен или Gate.io не инициализирован").open()
            return
        
        self.append_log("🧪 Запуск бэктеста на 1000 свечей...")
        self.append_log("⏳ Это может занять 30-60 секунд...")
        
        def backtest_thread():
            try:
                config = self.bot.config
                symbols = config['AS_SYMBOLS']
                timeframes = config['AS_TIMEFRAMES']
                leverage = config['LEVERAGE']
                trading_fee_pct = config.get('TRADING_FEE', 0.1) / 100
                
                current_balance = self.bot.gate.get_balance_usdt()
                if not current_balance or current_balance < 10:
                    Clock.schedule_once(lambda dt: Snackbar(text="⚠️ Недостаточный баланс").open(), 0)
                    return
                
                if config['ORDER_TYPE'] == 'percentage':
                    position_size_usdt = current_balance * (config['QTY_PERCENTAGE'] / 100)
                else:
                    position_size_usdt = config['FIXED_VOLUME']
                
                total_trades = 0
                winning_trades = 0
                total_pnl = 0.0
                
                for symbol in symbols:
                    for tf in timeframes:
                        Clock.schedule_once(lambda dt, s=symbol, t=tf: self.append_log(f"📊 Бэктест: {s} ({t})"), 0)
                        
                        df = self.bot.gate.get_ohlcv(symbol, tf, limit=1000)
                        if df.empty or len(df) < 150:
                            continue
                        
                        from synergy_bot_v7 import AdaptiveScalpingStrategy
                        as_strategy = AdaptiveScalpingStrategy(config, f"{symbol}_{tf}")
                        df = as_strategy.calculate_indicators(df.copy())
                        
                        position = None
                        entry_price = 0
                        symbol_trades = 0
                        symbol_wins = 0
                        symbol_pnl = 0.0
                        
                        for i in range(100, len(df)):
                            row = df.iloc[i]
                            if pd.isna(row.get('rsi')) or pd.isna(row.get('bb_pct')):
                                continue
                            
                            signal = None
                            if row['bb_pct'] < 0.1 and row['rsi'] < config['AS_RSI_OVERSOLD']:
                                signal = 'BUY'
                            elif row['bb_pct'] > 0.9 and row['rsi'] > config['AS_RSI_OVERBOUGHT']:
                                signal = 'SELL'
                            
                            if position:
                                tp_pct = config['AS_TAKE_PROFIT_PCT'] / 100
                                sl_pct = config['AS_STOP_LOSS_PCT'] / 100
                                
                                if position == 'LONG':
                                    high_pct = (row['high'] - entry_price) / entry_price
                                    low_pct = (row['low'] - entry_price) / entry_price
                                    
                                    if high_pct >= tp_pct:
                                        pnl = position_size_usdt * tp_pct * leverage
                                        fee = position_size_usdt * tp_pct * trading_fee_pct
                                        symbol_pnl += (pnl - fee)
                                        symbol_wins += 1
                                        symbol_trades += 1
                                        position = None
                                    elif low_pct <= -sl_pct:
                                        pnl = -position_size_usdt * sl_pct * leverage
                                        fee = position_size_usdt * sl_pct * trading_fee_pct
                                        symbol_pnl += (pnl - fee)
                                        symbol_trades += 1
                                        position = None
                                elif position == 'SHORT':
                                    low_pct = (entry_price - row['low']) / entry_price
                                    high_pct = (entry_price - row['high']) / entry_price
                                    
                                    if low_pct >= tp_pct:
                                        pnl = position_size_usdt * tp_pct * leverage
                                        fee = position_size_usdt * tp_pct * trading_fee_pct
                                        symbol_pnl += (pnl - fee)
                                        symbol_wins += 1
                                        symbol_trades += 1
                                        position = None
                                    elif high_pct <= -sl_pct:
                                        pnl = -position_size_usdt * sl_pct * leverage
                                        fee = position_size_usdt * sl_pct * trading_fee_pct
                                        symbol_pnl += (pnl - fee)
                                        symbol_trades += 1
                                        position = None
                            
                            if not position and signal:
                                position = 'LONG' if signal == 'BUY' else 'SHORT'
                                entry_price = row['close']
                        
                        if position and len(df) > 0:
                            last_price = df.iloc[-1]['close']
                            if position == 'LONG':
                                pnl = (last_price - entry_price) / entry_price * position_size_usdt * leverage
                            else:
                                pnl = (entry_price - last_price) / entry_price * position_size_usdt * leverage
                            symbol_pnl += pnl
                            symbol_trades += 1
                            if pnl > 0:
                                symbol_wins += 1
                        
                        total_trades += symbol_trades
                        winning_trades += symbol_wins
                        total_pnl += symbol_pnl
                        
                        win_rate = (symbol_wins / symbol_trades * 100) if symbol_trades > 0 else 0
                        Clock.schedule_once(lambda dt, s=symbol, t=tf, tr=symbol_trades, wr=win_rate, p=symbol_pnl: 
                            self.append_log(f"  ✅ {s} ({t}): {tr} сделок, WR={wr:.1f}%, PnL={p:+.2f}"), 0)
                
                win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
                
                result = f"""
{'='*60}
🧪 РЕЗУЛЬТАТЫ БЭКТЕСТА (1000 свечей)
{'='*60}
💵 Начальный баланс: {current_balance:.2f} USDT
📊 Размер позиции: {position_size_usdt:.2f} USDT
📈 Всего сделок: {total_trades}
✅ Прибыльных: {winning_trades}
📈 Win Rate: {win_rate:.1f}%
💰 Общий PnL: {total_pnl:+.2f} USDT
{'='*60}
"""
                Clock.schedule_once(lambda dt, r=result: self.append_log(r), 0)
                
            except Exception as ex:
                Clock.schedule_once(lambda dt, e=str(ex): self.append_log(f"❌ Ошибка бэктеста: {e}"), 0)
        
        thread = threading.Thread(target=backtest_thread, daemon=True)
        thread.start()
    
    def open_settings(self):
        """Открыть настройки"""
        config = load_config()
        
        # Создаем диалог настроек (упрощённая версия)
        self.tf_leverage = MDTextField(
            text=str(config['LEVERAGE']),
            hint_text="Кредитное плечо (например: 10)",
            mode="rectangle",
            size_hint_x=None,
            width=dp(200)
        )
        
        self.tf_qty = MDTextField(
            text=str(config['QTY_PERCENTAGE']),
            hint_text="% от баланса (например: 5)",
            mode="rectangle",
            size_hint_x=None,
            width=dp(200)
        )
        
        self.tf_volume = MDTextField(
            text=str(config['FIXED_VOLUME']),
            hint_text="Фиксированный объем USDT",
            mode="rectangle",
            size_hint_x=None,
            width=dp(200)
        )
        
        from kivy.uix.boxlayout import BoxLayout
        from kivymd.uix.button import MDButton, MDButtonText
        
        content = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(20))
        content.add_widget(MDLabel(text="⚙️ Настройки торговли", font_style="Title"))
        content.add_widget(self.tf_leverage)
        content.add_widget(self.tf_qty)
        content.add_widget(self.tf_volume)
        
        def save_settings(instance):
            try:
                lines = []
                with open('.env', 'r') as f:
                    lines = f.readlines()
                
                with open('.env', 'w') as f:
                    for line in lines:
                        if line.startswith('LEVERAGE='):
                            f.write(f"LEVERAGE={self.tf_leverage.text}\n")
                        elif line.startswith('QTY_PERCENTAGE='):
                            f.write(f"QTY_PERCENTAGE={self.tf_qty.text}\n")
                        elif line.startswith('FIXED_VOLUME='):
                            f.write(f"FIXED_VOLUME={self.tf_volume.text}\n")
                        else:
                            f.write(line)
                
                Snackbar(text="✅ Настройки сохранены. Перезапустите бота.").open()
                self.append_log("✅ Настройки сохранены")
                
                # Закрыть диалог
                if hasattr(self, 'settings_dialog'):
                    self.settings_dialog.dismiss()
            except Exception as e:
                Snackbar(text=f"❌ Ошибка: {e}").open()
        
        self.settings_dialog = MDDialog(
            title="Настройки",
            type="custom",
            content_cls=content,
            buttons=[
                MDButton(
                    MDButtonText(text="Отмена"),
                    style="text",
                    on_release=lambda x: self.settings_dialog.dismiss()
                ),
                MDButton(
                    MDButtonText(text="Сохранить"),
                    on_release=save_settings
                ),
            ],
        )
        self.settings_dialog.open()
    
    def _start_positions_carousel(self):
        """Запустить карусель позиций"""
        if self._carousel_running:
            return
        
        self._carousel_running = True
        self._carousel_index = 0
        
        def carousel_loop():
            while self._carousel_running:
                try:
                    if self.bot and self.bot.gate:
                        positions = self.bot.gate._normalize_positions(
                            self.bot.gate.futures_api.list_positions(settle='usdt')
                        )
                        open_positions = []
                        
                        for pos in positions:
                            if float(pos.size) != 0:
                                symbol = pos.contract
                                side = 'buy' if float(pos.size) > 0 else 'sell'
                                entry_price = float(pos.entry_price)
                                current_price = self.bot.gate.get_current_price(symbol) or entry_price
                                pnl = float(pos.unrealised_pnl)
                                margin = float(getattr(pos, 'margin', 0) or 0)
                                
                                if margin == 0:
                                    try:
                                        contract = self.bot.gate.futures_api.get_futures_contract(
                                            settle='usdt', contract=symbol
                                        )
                                        quanto_multiplier = float(contract.quanto_multiplier)
                                        size = abs(float(pos.size))
                                        leverage = float(getattr(pos, 'leverage', self.bot.config['LEVERAGE']))
                                        position_value = size * quanto_multiplier * entry_price
                                        if leverage > 0:
                                            margin = position_value / leverage
                                    except:
                                        pass
                                
                                pnl_pct = (pnl / margin * 100) if margin > 0.01 else 0
                                open_positions.append({
                                    'symbol': symbol,
                                    'side': side,
                                    'pnl': pnl,
                                    'pnl_pct': pnl_pct,
                                    'entry': entry_price,
                                    'current': current_price
                                })
                        
                        self._carousel_positions = open_positions
                        
                        if open_positions:
                            if self._carousel_index >= len(open_positions):
                                self._carousel_index = 0
                            
                            pos = open_positions[self._carousel_index]
                            pnl_sign = '+' if pos['pnl'] >= 0 else ''
                            pnl_color = "🟢" if pos['pnl'] >= 0 else "🔴"
                            
                            display_text = (
                                f"{pnl_color} {pos['symbol']} ({pos['side']}) | "
                                f"Вход: {pos['entry']:.4f} → {pos['current']:.4f} | "
                                f"{pnl_sign}{pos['pnl']:.2f} USDT ({pnl_sign}{pos['pnl_pct']:.2f}%)"
                            )
                            
                            self._carousel_index += 1
                        else:
                            display_text = "📊 Нет открытых позиций"
                        
                        Clock.schedule_once(lambda dt, t=display_text: self.update_positions_carousel(t), 0)
                    else:
                        Clock.schedule_once(lambda dt: self.update_positions_carousel("⏸️ Бот не запущен"), 0)
                    
                except Exception as e:
                    print(f"Ошибка карусели: {e}")
                
                time.sleep(4)
        
        thread = threading.Thread(target=carousel_loop, daemon=True)
        thread.start()
    
    def _stop_positions_carousel(self):
        """Остановить карусель"""
        self._carousel_running = False
    
    def toggle_background_service(self, checkbox):
        """Включить/выключить фоновую службу"""
        self.background_service_enabled = checkbox.active
        if checkbox.active:
            self.append_log("✅ Фоновая служба включена (будет работать при заблокированном экране)")
        else:
            self.append_log("ℹ️ Фоновая служба выключена")
            # Если служба запущена, остановить
            if self.bg_service.service_running:
                self.bg_service.stop_service()


# ==================== KIVYMD ПРИЛОЖЕНИЕ ====================
class SkalpmatApp(MDApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.theme_cls.material_style = "M3"
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Cyan"
    
    def build(self):
        Window.size = (400, 750)  # Размер окна для десктопа
        Window.minimum_width, Window.minimum_height = 300, 500
        
        # Создаём главный экран
        self.main_screen = MainScreen(name='main')
        
        # Верхняя панель
        top_toolbar = MDTopAppBar(
            pos_hint={"top": 1},
            type="small",
            title="SKALPMAT V7",
            left_action_items=[[]],
        )
        
        # Лог событий
        from kivymd.uix.label import MDLabel
        log_label = MDLabel(
            text=self.main_screen.log_text,
            halign="left",
            valign="top",
            font_name="RobotoMono-Regular",
            font_size="12sp",
            theme_text_color="Custom",
            text_color=(0, 1, 0, 1),  # Зелёный текст
        )
        
        # Привязка текста лога
        self.main_screen.bind(log_text=lambda inst, val: setattr(log_label, 'text', val))
        
        # Статус бар
        status_label = MDLabel(
            text=self.main_screen.status_text,
            halign="center",
            font_size="11sp",
            theme_text_color="Custom",
            text_color=(1, 1, 0, 1),  # Жёлтый
        )
        self.main_screen.bind(status_text=lambda inst, val: setattr(status_label, 'text', val))
        
        # Карусель позиций
        positions_label = MDLabel(
            text=self.main_screen.positions_text,
            halign="center",
            font_size="11sp",
            theme_text_color="Custom",
            text_color=(1, 1, 0, 1),
        )
        self.main_screen.bind(positions_text=lambda inst, val: setattr(positions_label, 'text', val))
        
        # PnL и баланс
        pnl_label = MDLabel(
            text="PnL: 0.00 USDT",
            halign="center",
            font_size="11sp",
            theme_text_color="Custom",
            text_color=(0, 1, 0, 1),
        )
        self.main_screen.bind(pnl_text=lambda inst, val: setattr(pnl_label, 'text', val))
        
        balance_label = MDLabel(
            text="Баланс: -- USDT",
            halign="center",
            font_size="11sp",
        )
        self.main_screen.bind(balance_text=lambda inst, val: setattr(balance_label, 'text', val))
        
        # Кнопки управления
        from kivy.uix.scrollview import ScrollView
        from kivy.uix.boxlayout import BoxLayout
        
        # Контейнер для кнопок
        buttons_layout = BoxLayout(
            orientation='vertical',
            size_hint_y=None,
            height=dp(320),
            spacing=dp(5),
            padding=dp(10)
        )
        
        # decidуй для кнопок
        btn_style = {
            'size_hint_y': None,
            'height': dp(50),
            'md_bg_color': self.theme_cls.primaryColor,
        }
        
        # Кнопка Старт/Стоп
        from kivy.metrics import dp as kivy_dp
        
        def create_button(text, on_press, color):
            btn = MDButton(
                MDButtonText(text=text, halign="center"),
                on_release=on_press,
                size_hint_y=None,
                height=kivy_dp(45),
                md_bg_color=color,
            )
            return btn
        
        # Создаём кнопки
        btn_start = create_button(
            "▶️ Старт",
            lambda x: self.main_screen.toggle_bot(),
            (0, 0.8, 0, 1)  # Зелёный
        )
        
        btn_positions = create_button(
            "📊 Позиции",
            lambda x: self.main_screen.show_positions(),
            (0, 0.6, 1, 1)  # Синий
        )
        
        btn_stats = create_button(
            "📈 Статистика",
            lambda x: self.main_screen.show_stats(),
            (0.6, 0, 1, 1)  # Фиолетовый
        )
        
        btn_report = create_button(
            "📋 Отчёт",
            lambda x: self.main_screen.show_report(),
            (0.2, 0.4, 1, 1)  # Голубой
        )
        
        btn_close = create_button(
            "❌ Закрыть всё",
            lambda x: self.main_screen.close_all_positions(),
            (1, 0, 0, 1)  # Красный
        )
        
        btn_backtest = create_button(
            "🧪 Бэктест",
            lambda x: self.main_screen.run_backtest(),
            (1, 0.6, 0, 1)  # Оранжевый
        )
        
        btn_settings = create_button(
            "⚙️ Настройки",
            lambda x: self.main_screen.open_settings(),
            (0.2, 0.5, 0.9, 1)
        )
        
        # Переключатель фоновой службы
        from kivymd.uix.boxlayout import MDBoxLayout
        from kivymd.uix.selectioncontrol import MDSwitch
        
        bg_service_layout = MDBoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=kivy_dp(50),
            spacing=kivy_dp(10),
            padding=kivy_dp(5)
        )
        
        lbl_bg_service = MDLabel(
            text="🌙 Работать в фоне (при заблокированном экране)",
            halign="left",
            valign="center",
            size_hint_x=0.7,
        )
        
        switch_bg_service = MDSwitch(
            active=False,
            on_active=lambda x, y: self.main_screen.toggle_background_service(x),
            size_hint_x=0.3,
        )
        
        bg_service_layout.add_widget(lbl_bg_service)
        bg_service_layout.add_widget(switch_bg_service)
        
        # Добавить все элементы в layout
        buttons_layout.add_widget(btn_start)
        buttons_layout.add_widget(btn_positions)
        buttons_layout.add_widget(btn_stats)
        buttons_layout.add_widget(btn_report)
        buttons_layout.add_widget(btn_close)
        buttons_layout.add_widget(btn_backtest)
        buttons_layout.add_widget(btn_settings)
        buttons_layout.add_widget(bg_service_layout)
        
        #ScrollView для кнопок (если не влезут)
        buttons_scroll = ScrollView(
            size_hint_y=None,
            height=kivy_dp(340),
        )
        buttons_scroll.add_widget(buttons_layout)
        
        # Главный вертикальный layout
        from kivy.uix.boxlayout import BoxLayout as KivyBoxLayout
        main_layout = KivyBoxLayout(orientation='vertical')
        main_layout.add_widget(top_toolbar)
        
        # Лог (скроллящийся)
        log_scroll = ScrollView(size_hint_y=0.5)
        log_scroll.add_widget(log_label)
        main_layout.add_widget(log_scroll)
        
        # Статус бары
        main_layout.add_widget(status_label)
        main_layout.add_widget(positions_label)
        main_layout.add_widget(pnl_label)
        main_layout.add_widget(balance_label)
        
        # Кнопки
        main_layout.add_widget(buttons_scroll)
        
        return main_layout
    
    def on_start(self):
        """Инициализация при запуске"""
        # Инициализация БД
        try:
            init_database()
            self.main_screen.append_log("✅ База данных инициализирована")
        except Exception as e:
            self.main_screen.append_log(f"❌ Ошибка БД: {e}")
        
        # Создание .env если нет
        if ensure_env_exists():
            self.main_screen.append_log("📄 Файл .env создан")
        
        # Запуск опроса очереди логов
        Clock.schedule_interval(self.poll_log_queue, 0.5)
    
    def poll_log_queue(self, dt):
        """Опрос очереди сообщений от бота"""
        if hasattr(self.main_screen, 'msg_queue'):
            batch = 0
            while not self.main_screen.msg_queue.empty() and batch < 50:
                try:
                    msg_type, text = self.main_screen.msg_queue.get_nowait()
                    if msg_type == 'log':
                        self.main_screen.append_log(text)
                    elif msg_type == 'status':
                        self.main_screen.update_status(text)
                    elif msg_type == 'pnl':
                        self.main_screen.update_pnl(*text)
                    batch += 1
                except:
                    break
        return True


if __name__ == "__main__":
    SkalpmatApp().run()