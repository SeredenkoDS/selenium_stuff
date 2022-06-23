import ctypes  # for msgbox
import pyperclip  # clipboard stuff
import secrets  # for random
import re  # for regexp
from functools import partial
from PySide2 import QtWidgets, QtGui
import threading
import traceback
import requests
import time
import sys
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.expected_conditions import presence_of_element_located
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import WebDriverException
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities


def open_notepad():  # just a showcase
    os.system('notepad')


def remaining_time_to_string(v_time):
    if v_time <= 0:
        return "about to start"
    else:
        time_limits = [1, 60, 3600, 86400, 604800, -777]
        time_symbols = ['?', 's', 'm+', 'h+', 'd+', 'w+']
        for v_i in range(1, len(time_limits)):
            if v_time < time_limits[v_i] or v_i == len(time_limits) - 1:
                return str(v_time // time_limits[v_i - 1]) + time_symbols[v_i]


def nullify_timer(required_task_id):
    global tasks_dict, remaining_time_modifier_lock, tray_icon
    remaining_time_modifier_lock.acquire()
    for task_dict in tasks_dict:
        if task_dict["task_id"] == required_task_id:
            task_dict["remaining_timer"] = 0
    remaining_time_modifier_lock.release()


def save_page_menu_func():
    chrome_options = Options()
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--headless")
    chrome_options.add_argument('window-size=1920x1080')
    chrome_options.add_argument("--log-level=3")  # disables the extra console messages
    chrome_options.add_argument("--user-data-dir=" + os.path.abspath("chrome_user_data"))
    try:
        driver = webdriver.Chrome(ChromeDriverManager().install(), options=chrome_options)
    except requests.exceptions.ConnectionError:
        return
    driver.set_window_size(1920, 1080)

    req_url = pyperclip.paste()
    driver.get(req_url)
    time.sleep(5)
    with open('page.html', 'wb') as f:
        f.write(driver.page_source.encode('utf-8'))
    driver.quit()
    ctypes.windll.user32.MessageBoxW(0, "Done saving into page.html.", "Scheduler", 0)


def quit_program():
    global quitting_flag
    quitting_flag = True


class SystemTrayIcon(QtWidgets.QSystemTrayIcon):
    def UpdateIcon(self):
        icon = QtGui.QIcon()
        icon.addPixmap(self.iconMovie.currentPixmap())
        if self.statusBusy:
            self.setIcon(icon)
        else:
            self.setIcon(self.staticIcon)

    def __init__(self, movie, parent=None):
        super(SystemTrayIcon, self).__init__(parent)
        self.setToolTip(f'Selenium scheduler')
        menu = QtWidgets.QMenu(parent)
        self.statusBusy = False
        self.staticIcon = QtGui.QIcon("icon.png")
        self.iconMovie = movie
        self.iconMovie.start()
        self.iconMovie.frameChanged.connect(self.UpdateIcon)

        tasks_menu = menu.addMenu("Tasks (click to run early)")
        tasks_menu.setIcon(QtGui.QIcon("icon.png"))
        debug_menu = menu.addMenu("Debug stuff")
        debug_menu.setIcon(QtGui.QIcon("icon.png"))

        def populate_submenu():
            global tasks_dict
            tasks_menu_actions = []
            tasks_sub_menu = QtWidgets.QMenu(parent)
            tasks_menu.clear()
            for task_dict in tasks_dict:
                menu_to_display = task_dict["desc"].replace("_", " ")
                if task_dict["last_result"] == "pending":
                    menu_to_display += " (pending)"
                else:
                    menu_to_display += " (" + remaining_time_to_string(task_dict["remaining_timer"]) + " until next)"
                my_action = tasks_sub_menu.addAction(menu_to_display)
                # my_action.triggered.connect(nullify_timer(task_dict["task_id"]))
                my_action.triggered.connect(partial(nullify_timer, task_dict["task_id"]))
                my_action.setIcon(QtGui.QIcon("icon.png"))
                tasks_menu_actions.append(my_action)
            # Step 3. Add the actions to the menu
            tasks_menu.addActions(tasks_menu_actions)

            # populating debug submenu
            debug_menu_actions = []
            debug_sub_menu = QtWidgets.QMenu(parent)
            debug_menu.clear()
            # menu 1 (just showing buffer contents)
            buffer_contents = pyperclip.paste()
            if len(buffer_contents) > 70:
                buffer_contents = buffer_contents[:30] + " ... " + buffer_contents[-30:]
            buffer_contents_action = debug_sub_menu.addAction("Buffer: " + buffer_contents)
            buffer_contents_action.setEnabled(False)
            buffer_contents_action.triggered.connect(quit_program)
            buffer_contents_action.setIcon(QtGui.QIcon("icon.png"))
            debug_menu_actions.append(buffer_contents_action)
            # menu 2 (save html page from clipboard URL)
            save_page_menu = debug_sub_menu.addAction("Save into page.html (uses URL from clipboard)")
            save_page_menu.triggered.connect(save_page_menu_func)
            save_page_menu.setIcon(QtGui.QIcon("icon.png"))
            debug_menu_actions.append(save_page_menu)

            # finally adding
            debug_menu.addActions(debug_menu_actions)
            # hiding it for now, don't need it anymore
            debug_menu.menuAction().setVisible(False)

        menu.aboutToShow.connect(populate_submenu)

        exit_ = menu.addAction("Exit")
        exit_.triggered.connect(quit_program)
        exit_.setIcon(QtGui.QIcon("icon.png"))

        menu.addSeparator()
        self.setContextMenu(menu)
        self.activated.connect(self.onTrayIconActivated)

        populate_submenu()

    def onTrayIconActivated(self, reason):
        """
        This function will trigger function on click or double click
        :param reason:
        :return:
        """
        if reason == self.DoubleClick:
            pass  # open_notepad()
        # if reason == self.Trigger:
        #     self.open_notepad()


def get_time_string(v_time, v_format='%Y-%m-%d-%H-%M-%S'):
    return time.strftime(v_format, time.localtime(v_time))


def ensure_dir(file_path):
    directory = os.path.dirname(file_path)
    if not os.path.exists(directory):
        os.makedirs(directory)


def update_tasks_file(who_calls):
    global update_tasks_file_lock, tasks_dict
    update_tasks_file_lock.acquire()
    print(who_calls, "update_file call started.")
    tasks_original_file = 'tasks.txt'
    tasks_renamed_file = 'tasks.renamed.txt'
    os.rename(tasks_original_file, tasks_renamed_file)
    file_new = open(tasks_original_file, "w")
    for tasks_dict_elem in tasks_dict:
        for tasks_dict_key in tasks_dict_elem:
            if tasks_dict_key == "original_timer":  # this one needs special treatment
                dict_to_write = ","
                for timer_value in tasks_dict_elem["original_timer"]:
                    dict_to_write += timer_value + ":" + str(tasks_dict_elem["original_timer"][timer_value]) + ","
                file_new.write("timer={" + dict_to_write[1:-1] + "} ")
            elif tasks_dict_key in ["task_id", "remaining_timer", "timer"]:
                pass  # don't need to save those
            else:
                file_new.write(tasks_dict_key + "=" + str(tasks_dict_elem[tasks_dict_key]) + " ")
        file_new.write("\n")
    file_new.close()
    os.remove(tasks_renamed_file)
    print(who_calls, "update_file call finished.")
    update_tasks_file_lock.release()


def task_handler(task_id):
    global tasks_dict, tray_icon
    # preparations, general for all tasks
    task_name = tasks_dict[task_id]["task_name"]
    log_file_name = "tasks/" + task_name + "/log.txt"
    ensure_dir(log_file_name)
    log_file = open(log_file_name, 'a')
    log_file.write("-----\n")
    log_file.write(task_name + " started at " + get_time_string(time.time(), "%Y-%m-%d %H:%M:%S") + "\n")
    # initializing browser...
    chrome_options = Options()
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--headless")
    chrome_options.add_argument('window-size=1920x1080')
    chrome_options.add_argument("--log-level=3")  # disables the extra console messages
    chrome_options.add_argument("--user-data-dir=" + os.path.abspath("chrome_user_data"))
    chrome_options.add_argument('--remote-debugging-port=9222')
    d = DesiredCapabilities.CHROME
    d['goog:loggingPrefs'] = {'browser': 'ALL'}
    try:
        driver = webdriver.Chrome(ChromeDriverManager().install(), options=chrome_options, desired_capabilities=d)
    except requests.exceptions.ConnectionError:
        log_file.write("Couldn't start ChromeDriver (possibly no internet or bad Chrome version?) Finishing early.\n")
        log_file.close()
        return "browser_init_fail"
    driver.set_window_size(1920, 1080)
    # browser init done.

    def visit_url(v_url):
        try:
            driver.get(v_url)
            return "visit_success"
        except WebDriverException:
            log_file.write("Couldn't visit " + v_url + " (timeout possibly?) Finishing early.\n")
            log_file.close()
            driver.quit()
            return "visit_fail"

    def log_and_exit(v_msg=None):
        if v_msg is None:
            log_file.write(task_name + " successfully ended at " + get_time_string(time.time(), "%Y-%m-%d %H:%M:%S"))
            log_file.write("\n")
        elif type(v_msg) is str:
            log_file.write(v_msg + "\n")
        else:  # likely an exception
            log_file.write("Something failed. Needs investigation: " + str(v_msg) + "\n")
            log_file.write(traceback.format_exc())
            log_file.write('\n.....\n')
        log_file.close()
        driver.quit()

    # ----------------------------------------------------------------------------------------------------
    if task_name == "summon_browser":
        if visit_url("https://google.com") == "visit_fail":
            return "visit_fail"
        while driver.current_url != 'about:about':
            time.sleep(1)
    # ----------------------------------------------------------------------------------------------------
    if task_name == 'check_liveuamap':
        if visit_url("https://liveuamap.com") == "visit_fail":
            return "visit_fail"
        try:
            element_wait = WebDriverWait(driver, 60)
            element_wait.until(presence_of_element_located((By.XPATH, '//div[@class="leaflet-pane '
                                                                      'leaflet-overlay-pane"]')))
            time.sleep(10)
            liveuamap_script = '''
                function del_by_class(v_class, v_index=0) {
                    v_element = document.getElementsByClassName(v_class)[v_index]
                    if (v_element != undefined) {
                        v_element.style.display = 'none'
                    } else {
                        console.log(v_class + " not found!")
                    }
                }
                del_by_class("header")
                del_by_class("leaflet-pane leaflet-marker-pane")
                del_by_class("leaflet-bottom leaflet-left")
                del_by_class("user-msg")
                del_by_class("leaflet-bottom leaflet-right")
            '''
            driver.execute_script(liveuamap_script)  # clears all the extra elements
            needed_element = driver.find_elements_by_xpath('//div[@id="map_canvas"]')[0]
            file_path = "tasks/" + task_name + "/" + get_time_string(time.time()) + ".png"
            ensure_dir(file_path)
            needed_element.screenshot(file_path)
            # for entry in driver.get_log('browser'):  # prints stuff from browser console
            #     print(entry)
        except Exception as e:
            log_and_exit(e)
            return "something_failed"
    # ----------------------------------------------------------------------------------------------------
    if task_name == 'genshin_daily_site_login':
        if visit_url("https://webstatic-sea.mihoyo.com/ys/event/signin-sea/index.html?act_id=e202102251931481&lang=en"
                     "-us") == "visit_fail":
            return "visit_fail"
        try:
            print("Waiting for 5 sec...")
            time.sleep(5)
            # print(driver.get_cookies())
            # driver.save_screenshot('tasks/' + task_name + "/" + str(time.time()) + ".png")
            element_wait = WebDriverWait(driver, 5)
            xpath_to_find = "//div[contains(@class, 'active')]"
            element_wait.until(presence_of_element_located((By.XPATH, xpath_to_find)))
        except TimeoutException:
            log_and_exit("Active element not found (already claimed daily rewards?)")
            return "element_not_found"

        try:
            element_active = driver.find_element_by_xpath(xpath_to_find)
            element_active.click()
            time.sleep(3)
            elem_login_form = driver.find_elements_by_xpath("//div[contains(@class, 'login-form-container')]")
            if len(elem_login_form) > 0:
                if elem_login_form[0].is_displayed():
                    log_and_exit("Apparently not logged in.")
                    tray_icon.showMessage('Selenium Scheduler', 'Genshin daily: not logged in?')
                    return "no_login"
        except Exception as e:
            log_and_exit(e)
            return "something_failed"

        log_and_exit()
        return "success"
    # ----------------------------------------------------------------------------------------------------
    if task_name == "daily_wordle":
        if visit_url("https://www.nytimes.com/games/wordle/index.html") == "visit_fail":
            return "visit_fail"

        try:  # close the popup if it pops
            time.sleep(3)
            close_button_script = "return document.querySelector('game-app')" + \
                ".shadowRoot.querySelector('game-modal').shadowRoot.querySelector('game-icon')"
            close_button = driver.execute_script(close_button_script)
            if close_button.is_displayed():
                close_button.click()
            time.sleep(3)
            print("Closed the popup.")
        except Exception as e:
            print("Something's wrong, close button is not pressed properly:", e)

        try:
            # reading words from file
            f_words = open("word_list.txt", "r")
            content = f_words.read()
            f_words.close()
            max_length = 5
            word_list = re.findall('[a-z]{5}', content)
            max_attempts = 6
            curr_word_results = 0
            min_dict, max_dict = {}, {}
            for ch_code in range(97, 123):
                min_dict[chr(ch_code)] = 0
                max_dict[chr(ch_code)] = max_length
            words_used_on_this_attempt = []
            new_pattern = ''  # just a useless row to get rid of the warning...
            for attempts in range(max_attempts):
                # print("----- #" + str(attempts + 1) + " ----- " + str(len(word_list)) + " words remaining")
                # print("Remaining words:", len(word_list))
                # selected_index = rigged_random(len(word_list))
                selected_index = secrets.randbelow(len(word_list))
                new_word = word_list[selected_index]
                get_word_script = '''let r = ''; for (step = 0; step < 5; step++) { b1 = document.querySelector(
                'game-app').shadowRoot.querySelectorAll('game-row')[''' + str(attempts) + \
                                  '''
                ].shadowRoot.querySelectorAll('game-tile')[
                step].shadowRoot.querySelector('div.tile'); a = b1.innerHTML; r += a; } return r; '''
                get_word = driver.execute_script(get_word_script)
                if get_word != '':
                    new_word = get_word
                else:
                    body_elem = driver.find_element_by_xpath("//body")
                    body_elem.send_keys(new_word)
                    body_elem.send_keys(Keys.ENTER)
                time.sleep(5)  # waiting for the animation to finish
                words_used_on_this_attempt.append(new_word)
                log_file.write("Word: " + new_word + " | ")
                print("Word: " + new_word + " | ", end="")
                # new_pattern = give_pattern(right_word, new_word)  # !! or receive pattern from the site instead
                get_status_script = '''let r = ''; for (step = 0; step < 5; step++) { b1 = document.querySelector(
                'game-app').shadowRoot.querySelectorAll('game-row')[''' + str(attempts) + \
                                    '''
                ].shadowRoot.querySelectorAll('game-tile')[step].shadowRoot.querySelector('div.tile');
                a = b1.getAttribute("data-state");
                if (a=='correct'){r += 'g'} 
                else if (a=='present'){r += 'y'} else if (a=='absent') {r+='b'} else {r += '?'}}; return r; '''
                new_pattern = driver.execute_script(get_status_script)
                log_file.write("Pattern: " + new_pattern + "\n")
                print("Pattern: " + new_pattern)
                if new_pattern == '?????':  # although I could probably handle it better than quitting immediately...
                    log_and_exit("Possibly trying a non-accepted word. Finishing early.")
                    return "word_not_accepted"
                if new_pattern == 'ggggg':
                    log_and_exit("Success!")
                    return "success"
                # print("Pattern: ", new_pattern)

                # let's count blacks, yellows and greens for each letter in the new_word
                for ch_c in new_word:
                    dict_byg = {'b': 0, 'y': 0, 'g': 0}
                    for ch_i in range(len(new_word)):
                        if new_word[ch_i] == ch_c:
                            dict_byg[new_pattern[ch_i]] += 1
                    # several same letters, some black, some green/yellow = exactly the number of g/y of such letters
                    # several same letters, no black, some green/yellow = minimum of g/y of such letters
                    sum_yg = dict_byg['y'] + dict_byg['g']  # weird random warnings here
                    if min_dict[ch_c] < sum_yg:
                        min_dict[ch_c] = sum_yg
                    if max_dict[ch_c] > sum_yg and dict_byg['b'] > 0:
                        max_dict[ch_c] = sum_yg

                for word_i in range(len(word_list) - 1, -1, -1):
                    delete_word = False
                    for ch_i in range(len(new_pattern)):
                        if new_pattern[ch_i] == 'g' and word_list[word_i][ch_i] != new_word[ch_i]:
                            delete_word = True
                        if new_pattern[ch_i] == 'y' and word_list[word_i][ch_i] == new_word[ch_i]:
                            delete_word = True
                    for ch_i in range(97, 123):
                        ch_count = word_list[word_i].count(chr(ch_i))
                        if ch_count > max_dict[chr(ch_i)]:
                            delete_word = True
                        if ch_count < min_dict[chr(ch_i)]:
                            delete_word = True
                    if delete_word:
                        word_list.pop(word_i)

                if not ('b' in new_pattern or 'y' in new_pattern):  # all green, we win
                    curr_word_results += attempts + 1
                    break

            if 'b' in new_pattern or 'y' in new_pattern:
                curr_word_results += max_attempts + 1
            # out of attempts, grabbing the correct word before finishing
            time.sleep(5)
            get_correct_word_script = "try { return document.querySelector('game-app').shadowRoot." + \
                                      "querySelector('game-toast').getAttribute('text') } catch (e) {" + \
                                      "return '<not displayed>' }"
            correct_word = driver.execute_script(get_correct_word_script)
            print("Out of attempts. Correct word is: " + correct_word.lower())
            log_and_exit("Out of attempts. Correct word is: " + correct_word.lower())
            return "out_of_attempts"
        except Exception as e:
            log_and_exit(e)
            return "something_failed"
    # ----------------------------------------------------------------------------------------------------

    log_and_exit()
    return "success"


def execute_task(task_id):
    global tasks_dict, remaining_time_modifier_lock
    # tasks_dict[task_id]["last_result"] = "pending"  # moved this to scheduler_function
    tasks_dict[task_id]["last_attempt_time"] = int(time.time())
    update_tasks_file(tasks_dict[task_id]["task_name"])
    # ### need to write actual task execution here later
    task_result = task_handler(task_id)
    # ### status update below
    tasks_dict[task_id]["last_result"] = task_result  # not only "success" now
    try:
        required_timer = tasks_dict[task_id]["timer"][task_result]
    except KeyError:
        try:
            required_timer = tasks_dict[task_id]["timer"]["*"]
        except KeyError:
            required_timer = 3600  # some default value of 1h
    remaining_time_modifier_lock.acquire()
    time_difference = int(time.time()) - tasks_dict[task_id]["last_attempt_time"]
    tasks_dict[task_id]["remaining_timer"] = required_timer - time_difference
    remaining_time_modifier_lock.release()
    tasks_dict[task_id]["last_attempt_time"] = int(time.time())
    update_tasks_file(tasks_dict[task_id]["task_name"])


def scheduler_function():
    global quitting_flag, tasks_dict, tray_icon
    global tasks_currently_executed, tasks_execution_limit, remaining_time_modifier_lock
    tasks_to_execute = []
    active_threads = []
    scheduler_initial_time = time.time()
    seconds_counter = 0  # just counting seconds, will be used to adjust sleep time
    while not quitting_flag:
        seconds_counter += 1
        for task_i, task_dict in enumerate(tasks_dict):
            remaining_time_modifier_lock.acquire()
            task_dict["remaining_timer"] -= 1
            remaining_time_modifier_lock.release()
            if task_dict["remaining_timer"] <= 0 and task_dict["last_result"] != "pending":
                task_dict["last_result"] = "pending"
                tasks_to_execute.append(task_i)
            # print(task_dict)  # debug stuff
        while tasks_currently_executed < tasks_execution_limit and len(tasks_to_execute) > 0:
            tasks_currently_executed += 1
            tray_icon.statusBusy = True  # animated icon if at least 1 task is running
            active_threads.append(0)
            active_threads[-1] = threading.Thread(target=execute_task, args=(tasks_to_execute[0],))
            tasks_to_execute.pop(0)
            active_threads[-1].start()

        active_len = len(active_threads)
        # debug part to check which threads are kept
        # print("current threads: ", end="")
        # for active_i in range(active_len):
        #     print(active_threads[active_i].is_alive(), end=" ")
        # print(len(tasks_to_execute))
        # end of debug part to check which threads are kept
        for active_i in range(active_len - 1, -1, -1):
            if not active_threads[active_i].is_alive():
                active_threads.pop(active_i)
                tasks_currently_executed -= 1
                if tasks_currently_executed == 0:
                    tray_icon.statusBusy = False  # static icon if no tasks are running

        remaining_sleep_time = seconds_counter - (time.time() - scheduler_initial_time)
        if remaining_sleep_time > 0:
            time.sleep(remaining_sleep_time)
        # more precise than just time.sleep(1), accounts for the time spent on previous rows of code

    # quit button is hit, wait for the remaining tasks to finish and exit (decided to not abort forcibly)
    while len(active_threads) > 0:  # just repeating the block higher, because I'm too lazy to do it more efficiently
        seconds_counter += 1
        active_len = len(active_threads)
        for active_i in range(active_len - 1, -1, -1):
            if not active_threads[active_i].is_alive():
                active_threads.pop(active_i)
                tasks_currently_executed -= 1
        remaining_sleep_time = seconds_counter - (time.time() - scheduler_initial_time)
        if remaining_sleep_time > 0:
            time.sleep(remaining_sleep_time)
    print("point of no return")


def convert_to_seconds(p_time):
    convert_dict = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    try:
        return int(p_time[:-1]) * convert_dict[p_time[-1]]
    except ValueError:
        return 88888888  # a default value if something fails
    except KeyError:
        try:
            return int(p_time)
        except Exception as e:
            print(e)
            return 88888888  # a default value if something fails


def init_icon():
    global tray_icon, init_icon_status
    if not os.path.exists("icon.png") or not os.path.exists("working.gif"):
        print("finishing early, no icon files")
        ctypes.windll.user32.MessageBoxW(0, "Either icon.png or working.gif is missing.", "Scheduler", 0x10)
        init_icon_status = "missing"
        return
    app = QtWidgets.QApplication(sys.argv)
    w = QtWidgets.QWidget()
    tray_icon = SystemTrayIcon(movie=QtGui.QMovie("working.gif"), parent=w)
    tray_icon.show()
    # tray_icon.showMessage('Some title', 'Some message')
    init_icon_status = "done"
    sys.exit(app.exec_())


tray_icon = 0  # moving tray_icon into global space
quitting_flag = False
update_tasks_file_lock = threading.Lock()
remaining_time_modifier_lock = threading.Lock()
file_tasks = open('tasks.txt', 'r')
task_lines = file_tasks.read().splitlines()
file_tasks.close()
tasks_currently_executed = 0
tasks_execution_limit = 1  # apparently chrome instances don't launch well at the same time... need lock otherwise
tasks_dict = []
task_assign_id = -1
for task_line in task_lines:
    task_assign_id += 1
    task_enabled = True
    task_split = task_line.split()
    tasks_dict.append({})
    tasks_dict[-1]["task_id"] = task_assign_id
    for task_split_elem in task_split:
        split_index = task_split_elem.find("=")
        split_part1 = task_split_elem[:split_index]
        split_part2 = task_split_elem[split_index + 1:]
        tasks_dict[-1][split_part1] = split_part2
        if split_part1 == "timer":
            tasks_dict[-1]["timer"] = {}
            tasks_dict[-1]["original_timer"] = {}
            split_timers = split_part2[1:-1].split(",")
            for timers_elem in split_timers:
                timer_index = timers_elem.find(":")
                split_timer_part1 = timers_elem[:timer_index]
                split_timer_part2 = timers_elem[timer_index + 1:]
                tasks_dict[-1]["original_timer"][split_timer_part1] = split_timer_part2
                tasks_dict[-1]["timer"][split_timer_part1] = convert_to_seconds(split_timer_part2)
        if split_part1 == "enabled" and split_part2.lower() != "true":
            task_enabled = False
    tasks_dict[-1]["last_attempt_time"] = int(tasks_dict[-1]["last_attempt_time"])
    time_passed_since_last_try = int(time.time()) - tasks_dict[-1]["last_attempt_time"]
    if tasks_dict[-1]["last_result"] == "pending":
        tasks_dict[-1]["last_result"] = "fail"  # an indication that maybe program crashed while executing
    try:
        last_task_result = tasks_dict[-1]["last_result"]
        tasks_dict[-1]["remaining_timer"] = tasks_dict[-1]["timer"][last_task_result] - time_passed_since_last_try
    except KeyError:
        try:
            tasks_dict[-1]["remaining_timer"] = tasks_dict[-1]["timer"]["*"] - time_passed_since_last_try
        except KeyError:
            tasks_dict[-1]["remaining_timer"] = 86400  # some default set value
    if not task_enabled:
        tasks_dict.pop()

init_icon_status = "started"
icon_thread = threading.Thread(target=init_icon, args=(), daemon=True)
icon_thread.start()
while not init_icon_status == "done":
    if init_icon_status == "missing":
        raise SystemExit
scheduler_thread = threading.Thread(target=scheduler_function, args=())
scheduler_thread.start()
# pyinstaller --onefile --noconsole tray_playground.py
