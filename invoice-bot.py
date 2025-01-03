from fpdf import FPDF
import os
import json
from telegram import ReplyKeyboardMarkup, KeyboardButton, Contact
from telegram.ext import Application, CommandHandler, MessageHandler, filters
import logging
import arabic_reshaper
from bidi.algorithm import get_display
import jdatetime  # Import the library
from PIL import Image
import io
import re
import textwrap
from datetime import datetime

dollarFee = 83600 # Example multiplier
# تنظیمات اولیه
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# مسیر فایل JSON برای ذخیره‌سازی اطلاعات
USER_DATA_FILE = 'user_data.json'

# تابع ذخیره‌سازی اطلاعات کاربر
def save_user_data(user_id, data):
    if os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, 'r', encoding='utf-8') as file:
            user_data = json.load(file)
    else:
        user_data = {}

    user_data[str(user_id)] = data
    with open(USER_DATA_FILE, 'w', encoding='utf-8') as file:
        json.dump(user_data, file, ensure_ascii=False, indent=4)

# تابع دریافت اطلاعات کاربر
def get_user_data(user_id):
    if os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, 'r', encoding='utf-8') as file:
            user_data = json.load(file)
            return user_data.get(str(user_id), {})
    return {}

def update_user_state(user_id, state):
    user_data = get_user_data(user_id)
    user_data['state'] = state
    save_user_data(user_id, user_data)

def get_user_state(user_id):
    user_data = get_user_data(user_id)
    return user_data.get('state', 'ready')


# کلاس ایجاد فاکتور
class InvoicePDF(FPDF):
    
    def header(self):
        # Only add the header on the first page
        if self.page_no() == 1:
            # Add the font
            if os.path.exists('Vazir.ttf'):
                self.add_font('Vazir', '', 'Vazir.ttf', uni=True)
                self.set_font('Vazir', '', 14)
            else:
                self.set_font('Arial', '', 14)
                logger.warning("فایل فونت یافت نشد، از Arial استفاده می‌شود.")

            # Add the logo (aligned to the right)
            logo_path = f'logos/{self.user_id}.png'  # Adjust based on your storage structure
            if os.path.exists(logo_path):
                self.image(logo_path, x=170, y=10, w=30)  # Logo on the right

            # Add the title (centered horizontally)
            title = get_display(arabic_reshaper.reshape('به نام ایزد یکتا'))
            self.set_xy(10, 15)  # Position cursor for the title
            self.cell(0, 10, title, align='C', ln=True)  # Center the title in the row

            # Add the additional lines
            line1 = get_display(arabic_reshaper.reshape('فاکتور فروش'))
            line2 = get_display(arabic_reshaper.reshape('خانه هوشمند کهربا'))
            self.set_font('Vazir', '', 12)  # Adjust font size for these lines
            self.cell(0, 10, line1, align='C', ln=True)  # First additional line
            self.cell(0, 10, line2, align='C', ln=True)  # Second additional line

            # Add spacing after the header
            self.ln(10)

            # Seller Info
            user_data = get_user_data(self.user_id)
            store_name = user_data.get('store_name', 'نام فروشگاه تعریف نشده')
            seller_name = user_data.get('seller_name', 'نام فروشنده تعریف نشده')
            current_date = jdatetime.date.today().strftime('%Y/%m/%d')

            # Generate the unique invoice number
            current_datetime = datetime.now().strftime("%y%m%d%H%M")
            customer_code = self.customer["code"] if self.customer else "0000"
            invoice_number = f"{current_datetime}{customer_code}"

            # Layout adjustments for Seller Info
            self.set_font('Vazir' if os.path.exists('Vazir.ttf') else 'Arial', '', 12)
            self.cell(95, 10, get_display(arabic_reshaper.reshape(f'تاریخ: {current_date}')), 1, 0, 'R')
            self.cell(95, 10, get_display(arabic_reshaper.reshape(f'شماره فاکتور: {invoice_number}')), 1, 1, 'R')
            self.cell(95, 10, get_display(arabic_reshaper.reshape(f'توسط: {seller_name}')), 1, 0, 'R')
            self.cell(95, 10, get_display(arabic_reshaper.reshape(f'فروشگاه: {store_name}')), 1, 1, 'R')
            self.ln(2)  # Space after seller info

            # Add customer details
            customer = self.customer
            if customer:
                self.cell(95, 10, get_display(arabic_reshaper.reshape(f'نام مشتری: {customer["name"]}')), 1, 0, 'R')
                self.cell(95, 10, get_display(arabic_reshaper.reshape(f'شماره تماس: {customer["phone"]}')), 1, 1, 'R')
                self.cell(95, 10, get_display(arabic_reshaper.reshape(f'آدرس: {customer["address"]}')), 1, 0, 'R')
                self.cell(95, 10, get_display(arabic_reshaper.reshape(f'کد مشتری: {customer["code"]}')), 1, 1, 'R')
            self.ln(10)
        else:
            # If not the first page, we just return without doing anything (no header)
            pass

    def footer(self):
        # Move to the last available position after the items
        self.ln(10)  # Add space before the footer

        # Prepare the footer content
        self.set_font('Vazir' if os.path.exists('Vazir.ttf') else 'Arial', '', 10)
        
        description = get_display(arabic_reshaper.reshape(
            '• با توجه به نوسانات نرخ ارز اعتبار پیش فاکتور تنها یک روز می باشد.'
        ))
        contact = get_display(arabic_reshaper.reshape('• شماره تماس 09109359043'))
        
        # Add the lines to the PDF (right-aligned)
        self.cell(0, 10, description, align='R', ln=True)
        self.cell(0, 10, contact, align='R', ln=True)
        
        # Additional spacing after bullet points (if needed)
        self.ln(5)

    def invoice_body(self, items):
        global dollarFee  # Use the global dollarFee variable

        # Step 1: Calculate the total price of items after applying dollarFee
        total_price = 0
        for idx, item in enumerate(items, start=1):
            name, quantity, unit_price = item

            # Apply dollarFee multiplier to the unit price
            adjusted_unit_price = unit_price * dollarFee
            
            # Round the adjusted unit price to the nearest multiple of 1000
            adjusted_unit_price = round(adjusted_unit_price / 1000) * 1000
            
            total = quantity * adjusted_unit_price
            total_price += total

        # Step 2: Calculate the "اجرت نصب" (installation fee) as 20% of the total price
        installation_fee = total_price * 0.20  # 20% of the total price
        installation_fee = round(installation_fee / 1000) * 1000  # Round to the nearest 1000

        # Step 3: Table Header for products (excluding installation fee)
        self.set_font('Vazir' if os.path.exists('Vazir.ttf') else 'Arial', '', 12)
        self.cell(40, 10, get_display(arabic_reshaper.reshape('قیمت کل (تومان)')), 1, 0, 'C')
        self.cell(40, 10, get_display(arabic_reshaper.reshape('قیمت واحد (تومان)')), 1, 0, 'C')
        self.cell(15, 10, get_display(arabic_reshaper.reshape('تعداد')), 1, 0, 'C')
        self.cell(83, 10, get_display(arabic_reshaper.reshape('شرح کالا یا خدمات')), 1, 0, 'C')
        self.cell(12, 10, get_display(arabic_reshaper.reshape('ردیف')), 1, 1, 'C')

        # Step 4: Table Body for products
        total_price = 0
        self.set_font('Vazir' if os.path.exists('Vazir.ttf') else 'Arial', '', 12)
        for idx, item in enumerate(items, start=1):
            name, quantity, unit_price = item

            # Apply dollarFee multiplier to the unit price
            adjusted_unit_price = unit_price * dollarFee
            
            # Round the adjusted unit price to the nearest multiple of 1000
            adjusted_unit_price = round(adjusted_unit_price / 1000) * 1000
            
            total = quantity * adjusted_unit_price
            total_price += total

            idx_text = str(idx)
            quantity_text = str(quantity)
            unit_price_text = get_display(arabic_reshaper.reshape(f'{adjusted_unit_price:,}'))
            total_text = get_display(arabic_reshaper.reshape(f'{total:,}'))

            # Wrap product name intelligently at spaces
            name_text = get_display(arabic_reshaper.reshape(name))
            max_width = 38  # Maximum characters per line
            wrapped_lines = textwrap.wrap(name_text, width=max_width, break_long_words=False)

            # Reverse the order of wrapped lines for correct Arabic/Persian display
            wrapped_lines = wrapped_lines[::-1]  
            wrapped_name = "\n".join(wrapped_lines)

            # Calculate the required height for the cell
            line_height = 8  # Adjust the line height for better spacing
            num_lines = len(wrapped_lines)
            cell_height = line_height * num_lines

            # Align other cells to match the height of the name cell
            self.cell(40, cell_height, total_text, 1, 0, 'C')
            self.cell(40, cell_height, unit_price_text, 1, 0, 'C')
            self.cell(15, cell_height, quantity_text, 1, 0, 'C')

            # Handle multi-line for product name
            x = self.get_x()
            y = self.get_y()
            self.multi_cell(83, line_height, wrapped_name, 1, 'C')
            self.set_xy(x + 83, y)  # Reset X position after multi_cell

            self.cell(12, cell_height, idx_text, 1, 1, 'C')  # Move to the next line

        # Step 5: Display Installation Fee as a separate item
        installation_fee_text = get_display(arabic_reshaper.reshape(f"{installation_fee:,}"))
        self.cell(40, 10, installation_fee_text, 1, 0, 'C')
        self.cell(150, 10, get_display(arabic_reshaper.reshape('اجرت نصب و راه‌اندازی سیستم')), 1, 1, 'R')

        # Step 6: Total Price (including اجرت نصب)
        total_price_with_installation = total_price + installation_fee
        total_price_text = get_display(arabic_reshaper.reshape(f'{total_price_with_installation:,} تومان'))
        self.cell(40, 10, total_price_text, 1, 0, 'C')
        self.cell(150, 10, get_display(arabic_reshaper.reshape('جمع کل')), 1, 1, 'R')





# تابع ایجاد فاکتور



def generate_invoice_pdf(items, user_id, customer=None):
    # Generate the unique invoice number and file name
    current_datetime = datetime.now().strftime("%y%m%d%H%M")
    customer_code = customer["code"] if customer else "0000"
    invoice_number = f"{current_datetime}{customer_code}"

    # Create folder for the user if it doesn't exist
    user_folder = os.path.join("invoiceFiles", str(user_id))
    os.makedirs(user_folder, exist_ok=True)

    # Create the invoice file name with invoice number and customer name
    customer_name = customer["name"] if customer else "Unknown"
    invoice_filename = f"{invoice_number}_{customer_name}.pdf"
    file_path = os.path.join(user_folder, invoice_filename)

    # Generate the PDF invoice
    pdf = InvoicePDF()
    pdf.customer = customer
    pdf.user_id = user_id
    pdf.invoice_number = invoice_number  # Pass the invoice number to the header

    pdf.add_page()
    pdf.invoice_body(items)
    pdf.output(file_path)

    return file_path  # Return the full path of the generated invoice


# تابع مدیریت بات تلگرام
async def start(update, context):
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    if 'phone_number' in user_data:
        # اگر شماره تلفن قبلا ذخیره شده بود، مستقیما منوی افزودن آیتم و صدور فاکتور را نمایش دهد
        keyboard = [ [KeyboardButton("افزودن محصول"), KeyboardButton("مشاهده محصولات")],
        [KeyboardButton("افزودن آیتم"), KeyboardButton("صدور فاکتور")],
        [KeyboardButton("افزودن مشتری"), KeyboardButton("مشاهده مشتریان")],
        [KeyboardButton("انتخاب مشتری"), KeyboardButton("آپلود لوگوی فروشگاه")]]
        
        update_user_state(user_id, 'ready')  # Reset state
        reply_markup = ReplyKeyboardMarkup(keyboard)
        await update.message.reply_text('سلام! لطفاً انتخاب کنید:', reply_markup=reply_markup)
    else:
        # اگر شماره تلفن ذخیره نشده بود، درخواست اشتراک‌گذاری شماره تلفن را ارسال کند
        contact_keyboard = KeyboardButton(text="اشتراک‌گذاری شماره تلفن", request_contact=True)
        reply_markup = ReplyKeyboardMarkup([[contact_keyboard]], one_time_keyboard=True)
        await update.message.reply_text('لطفاً شماره تلفن خود را به اشتراک بگذارید:', reply_markup=reply_markup)

async def contact_handler(update, context):
    contact: Contact = update.effective_message.contact
    user_id = update.effective_user.id
    phone_number = contact.phone_number
    user_data = get_user_data(user_id)
    user_data['phone_number'] = phone_number
    user_data['state'] = 'awaiting_store_info'
    save_user_data(user_id, user_data)
    await update.message.reply_text('شماره تلفن شما ذخیره شد. لطفاً نام فروشگاه و نام فروشنده را به شکل زیر وارد کنید:\n\nفروشگاه: نام فروشگاه - فروشنده: نام فروشنده')

async def handle_store_info(update, context):
    user_id = str(update.effective_user.id)
    user_data = get_user_data(user_id)

    if user_data.get('state') != 'awaiting_store_info':
        return False  # State does not match, so return and continue to next handler

    try:
        store_info = update.message.text.split('-')
        store_name = store_info[0].split(':')[1].strip()
        seller_name = store_info[1].split(':')[1].strip()
        user_data['store_name'] = store_name
        user_data['seller_name'] = seller_name
        user_data['state'] = 'ready'
        save_user_data(user_id, user_data)
        await update.message.reply_text('اطلاعات فروشگاه شما ذخیره شد.')
        return True  # Input processed successfully
    except (IndexError, ValueError):
        return False  # Return False to allow other handlers to process the input



async def handle_add_item(update, context):
    user_id = str(update.effective_user.id)
    user_data = get_user_data(user_id)

    if user_data.get('state') != 'adding_item':
        return False  # State does not match, so return and continue to next handler

    product_id = update.message.text.strip()
    products = user_data.get('products', {})

    if product_id not in products:
        await update.message.reply_text(f"محصولی با ID '{product_id}' یافت نشد.")
        return False  # Return False to allow other handlers to process the input

    product = products[product_id]
    if 'items' not in context.user_data:
        context.user_data['items'] = []

    context.user_data['items'].append((product['name'], 1, product['price']))
    user_data['state'] = 'ready'  # Reset state after adding the item
    save_user_data(user_id, user_data)

    await update.message.reply_text(f"محصول '{product['name']}' به فاکتور اضافه شد.")
    return True  # Input processed successfully


async def add_item_handler(update, context):
    user_id = str(update.effective_user.id)
    user_data = get_user_data(user_id)

    products = user_data.get('products', {})
    if not products:
        await update.message.reply_text("شما هیچ محصولی ثبت نکرده‌اید. ابتدا از گزینه 'افزودن محصول' استفاده کنید.")
        return

    # Generate a dynamic keyboard with product names
    keyboard = [[KeyboardButton(f"{product['name']} (ID: {product_id})")] for product_id, product in products.items()]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)

    # Update user state
    user_data['state'] = 'selecting_product'
    save_user_data(user_id, user_data)

    await update.message.reply_text("لطفاً محصول مورد نظر را انتخاب کنید:", reply_markup=reply_markup)

async def handle_product_selection(update, context):
    user_id = str(update.effective_user.id)
    user_data = get_user_data(user_id)

    if user_data.get('state') != 'selecting_product':
        return  # Ignore if the user is not selecting a product.

    # Extract product ID from the selected text
    selected_text = update.message.text
    product_id = selected_text.split("(ID:")[1].split(")")[0].strip()

    products = user_data.get('products', {})
    if product_id not in products:
        await update.message.reply_text("محصول انتخاب‌شده معتبر نیست. لطفاً دوباره تلاش کنید.")
        return

    # Save the selected product ID and update state
    context.user_data['selected_product'] = product_id
    user_data['state'] = 'awaiting_quantity'
    save_user_data(user_id, user_data)

    await update.message.reply_text(
        f"محصول '{products[product_id]['name']}' انتخاب شد. لطفاً تعداد آن را با پیشوند 'q' وارد کنید (مثال: q3 برای تعداد 3)."
    )

from telegram import ReplyKeyboardMarkup, KeyboardButton

async def handle_quantity_input(update, context):
    user_id = str(update.effective_user.id)
    user_data = get_user_data(user_id)

    # Check the state
    if user_data.get('state') != 'awaiting_quantity':
        return  # Ignore if the user is not entering a quantity.

    # Extract the quantity from the message (e.g., "q3")
    quantity_match = re.match(r"[Qq](\d+)", update.message.text.strip(), re.IGNORECASE)
    if not quantity_match:
        await update.message.reply_text("فرمت تعداد معتبر نیست. لطفاً از پیشوند 'q' استفاده کنید (مثال: q3 برای تعداد 3).")
        return

    quantity = int(quantity_match.group(1))
    if quantity <= 0:
        await update.message.reply_text("تعداد باید بیشتر از صفر باشد.")
        return

    # Retrieve the selected product
    product_id = context.user_data.get('selected_product')
    if not product_id:
        await update.message.reply_text("محصول انتخاب‌شده معتبر نیست. لطفاً دوباره تلاش کنید.")
        return

    products = user_data.get('products', {})
    product = products[product_id]

    # Add the item to the invoice
    if 'items' not in context.user_data:
        context.user_data['items'] = []

    context.user_data['items'].append((product['name'], quantity, product['price']))

    # Reset user state
    user_data['state'] = 'ready'
    save_user_data(user_id, user_data)

    # Initial keyboard
    keyboard = [
        [KeyboardButton("افزودن محصول"), KeyboardButton("مشاهده محصولات")],
        [KeyboardButton("افزودن آیتم"), KeyboardButton("صدور فاکتور")],
        [KeyboardButton("افزودن مشتری"), KeyboardButton("مشاهده مشتریان")],
        [KeyboardButton("انتخاب مشتری"), KeyboardButton("آپلود لوگوی فروشگاه")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"محصول '{product['name']}' با تعداد {quantity} به فاکتور اضافه شد.",
        reply_markup=reply_markup
    )


async def add_product_handler(update, context):
    user_id = str(update.effective_user.id)
    user_data = get_user_data(user_id)
    if 'products' not in user_data:
        user_data['products'] = {}

    update_user_state(user_id, 'adding_product')
    await update.message.reply_text(
        "لطفاً محصول خود را به شکل زیر وارد کنید:\n\nنام محصول-قیمت واحد\n\nمثال: نازل-10000"
    )
    

async def add_product(update, context):
    user_id = str(update.effective_user.id)
    user_data = get_user_data(user_id)

    if user_data.get('state') != 'adding_product':
        return False  # State does not match, so return and continue to next handler

    try:
        product_info = update.message.text.split('-')
        name = product_info[0].strip()
        price = int(product_info[1].strip())
        last_product_id = user_data['last_product_id']
        product_id = f"{user_id}-{last_product_id + 1}"  # Unique ID per user
        user_data['last_product_id'] = last_product_id + 1
        user_data['products'][product_id] = {"name": name, "price": price}
        user_data['state'] = 'ready'
        save_user_data(user_id, user_data)
        await update.message.reply_text(f"محصول '{name}' با قیمت {price} تومان اضافه شد. شناسه محصول: {product_id}")
        return True  # Input processed successfully
    except (IndexError, ValueError):
        return False  # Return False to allow other handlers to process the input



async def view_products(update, context):
    user_id = str(update.effective_user.id)
    user_data = get_user_data(user_id)
    products = user_data.get('products', {})
    if not products:
        await update.message.reply_text("شما هیچ محصولی ثبت نکرده‌اید.")
        return

    product_list = "لیست محصولات شما:\n"
    for product_id, product in products.items():
        product_list += f"ID: {product_id}, نام: {product['name']}, قیمت: {product['price']} تومان\n"
    await update.message.reply_text(product_list)


async def store_logo_handler(update, context):
    user_id = str(update.effective_user.id)
    user_data = get_user_data(user_id)

    # Check if the user is in the correct state
    if user_data.get('state') != 'awaiting_logo_upload':
        await update.message.reply_text("لطفاً ابتدا گزینه 'آپلود لوگوی فروشگاه' را انتخاب کنید.")
        return

    # Check if a photo is included in the update
    if not update.message.photo:
        await update.message.reply_text("لطفاً یک عکس ارسال کنید.")
        return

    # Get the highest resolution photo (last in the list)
    photo_file = await update.message.photo[-1].get_file()

    # Download the photo to a temporary location
    temp_file = io.BytesIO()
    await photo_file.download_to_memory(out=temp_file)
    temp_file.seek(0)

    # Convert the image to PNG format
    try:
        image = Image.open(temp_file)
        logo_dir = 'logos'
        os.makedirs(logo_dir, exist_ok=True)
        file_path = os.path.join(logo_dir, f"{user_id}.png")
        image.save(file_path, format="PNG")
    except Exception as e:
        await update.message.reply_text(f"خطایی رخ داد: {str(e)}")
        return

    # Reset the user state
    user_data['state'] = 'ready'
    save_user_data(user_id, user_data)

    await update.message.reply_text("لوگوی فروشگاه شما با موفقیت ذخیره شد.")


async def prompt_upload_logo_handler(update, context):
    user_id = str(update.effective_user.id)
    user_data = get_user_data(user_id)
    user_data['state'] = 'awaiting_logo_upload'
    save_user_data(user_id, user_data)
    await update.message.reply_text("لطفاً لوگوی فروشگاه خود را به عنوان یک عکس ارسال کنید.")

async def add_customer_handler(update, context):
    user_id = str(update.effective_user.id)
    user_data = get_user_data(user_id)
    user_data['state'] = 'adding_customer'
    save_user_data(user_id, user_data)

    await update.message.reply_text(
        "لطفاً اطلاعات مشتری را به شکل زیر وارد کنید:\n\n"
        "نام - شماره تلفن - آدرس - کد مشتری\n\n"
        "مثال: علی احمدی - 09123456789 - تهران، میدان آزادی - CUST001"
    )

async def save_customer(update, context):
    user_id = str(update.effective_user.id)
    user_data = get_user_data(user_id)

    if user_data.get('state') != 'adding_customer':
        return False  # State does not match, so return and continue to next handler

    try:
        customer_info = update.message.text.split('-')
        name = customer_info[0].strip()
        phone = customer_info[1].strip()
        address = customer_info[2].strip()
        code = customer_info[3].strip()

        if 'customers' not in user_data:
            user_data['customers'] = {}

        user_data['customers'][code] = {"name": name, "phone": phone, "address": address, "code": code}
        user_data['state'] = 'ready'
        save_user_data(user_id, user_data)

        await update.message.reply_text(f"مشتری '{name}' با کد '{code}' ذخیره شد.")
        return True  # Input processed successfully
    except (IndexError, ValueError):
        return False  # Return False to allow other handlers to process the input



async def view_customers(update, context):
    user_id = str(update.effective_user.id)
    user_data = get_user_data(user_id)

    customers = user_data.get('customers', {})
    if not customers:
        await update.message.reply_text("شما هیچ مشتری‌ای ثبت نکرده‌اید.")
        return

    customer_list = "لیست مشتریان شما:\n"
    for code, customer in customers.items():
        customer_list += f"کد: {code}, نام: {customer['name']}, شماره: {customer['phone']}, آدرس: {customer['address']}\n"

    await update.message.reply_text(customer_list)


from telegram import ReplyKeyboardMarkup, KeyboardButton

async def select_customer_handler(update, context):
    user_id = str(update.effective_user.id)
    user_data = get_user_data(user_id)

    customers = user_data.get('customers', {})
    if not customers:
        await update.message.reply_text("شما هیچ مشتری‌ای ثبت نکرده‌اید. ابتدا مشتری اضافه کنید.")
        return

    # Prepare a dynamic keyboard with customer names
    keyboard = [[KeyboardButton(customer["name"])] for customer in customers.values()]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)

    # Ask the user to select a customer
    await update.message.reply_text("لطفاً مشتری مورد نظر خود را انتخاب کنید:", reply_markup=reply_markup)

    # Update the user state to 'selecting_customer'
    user_data['state'] = 'selecting_customer'
    save_user_data(user_id, user_data)



async def save_selected_customer(update, context):
    user_id = str(update.effective_user.id)
    user_data = get_user_data(user_id)

    if user_data.get('state') != 'selecting_customer':
        await update.message.reply_text("دستور نامعتبر است.")
        return False

    # Get the selected customer name
    selected_name = update.message.text.strip()
    customers = user_data.get('customers', {})

    # Find the customer based on the name
    selected_customer = None
    for customer in customers.values():
        if customer["name"] == selected_name:
            selected_customer = customer
            break

    if not selected_customer:
        await update.message.reply_text(f"مشتری با نام '{selected_name}' یافت نشد. لطفاً دوباره تلاش کنید.")
        return False

    # Save the selected customer in the context
    context.user_data['selected_customer'] = selected_customer
    user_data['state'] = 'ready'
    save_user_data(user_id, user_data)

    # Send confirmation message with the selected customer
    await update.message.reply_text(
        f"مشتری '{selected_customer['name']}' انتخاب شد."
    )

    # Show the main menu again
    keyboard = [
        [KeyboardButton("افزودن محصول"), KeyboardButton("مشاهده محصولات")],
        [KeyboardButton("افزودن آیتم"), KeyboardButton("صدور فاکتور")],
        [KeyboardButton("افزودن مشتری"), KeyboardButton("مشاهده مشتریان")],
        [KeyboardButton("انتخاب مشتری"), KeyboardButton("آپلود لوگوی فروشگاه")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard)
    await update.message.reply_text('لطفاً انتخاب کنید:', reply_markup=reply_markup)
    return True



async def generate_invoice(update, context):
    user_id = update.effective_user.id
    items = context.user_data.get('items', [])
    customer = context.user_data.get('selected_customer')

    if not items:
        await update.message.reply_text("هیچ آیتمی برای صدور فاکتور وجود ندارد.")
        return

    if not customer:
        await update.message.reply_text("لطفاً ابتدا یک مشتری انتخاب کنید.")
        return

    # Generate the invoice file and get the file path
    file_path = generate_invoice_pdf(items=items, user_id=user_id, customer=customer)

    # Send the invoice file with the correct name
    with open(file_path, 'rb') as file:
        await update.message.reply_document(document=file)

    # Clear items and customer after sending the invoice
    context.user_data['items'] = []
    context.user_data['selected_customer'] = None

    await update.message.reply_text("فاکتور شما صادر شد.")


async def handle_input(update, context, handlers):
        """
        Iterates over the handlers and calls the first one that can process the input.
        """
        for handler in handlers:
            # Check if the handler can process the input
            if await handler(update, context):
                return  # Exit as the handler has processed the input
        # If no handler processed the input, continue to the next one
        await update.message.reply_text("فرمت وارد شده معتبر نیست یا در حال حاضر قابل پردازش نیست.")


async def main_handler(update, context):
    handlers = [add_product, save_customer,save_selected_customer, handle_store_info, handle_add_item]
    await handle_input(update, context, handlers)


# تابع اصلی
def main():
    # توکن بات خود را اینجا وارد کنید
    application = Application.builder().token("7519056333:AAHY5c1yScb9ezdeJwpkL3FJVnVlf2XsPuM").build()

    # اضافه کردن هندلرها
    application.add_handler(CommandHandler("start", start))                         # Start the bot
    application.add_handler(MessageHandler(filters.CONTACT, contact_handler))       # Handle contact sharing
    application.add_handler(MessageHandler(filters.Regex('^مشاهده محصولات$'), view_products))     # View Products
    application.add_handler(MessageHandler(filters.Regex('^افزودن محصول$'), add_product_handler))  # Add Product
    application.add_handler(MessageHandler(filters.Regex('^صدور فاکتور$'), generate_invoice))     # Generate Invoice
    application.add_handler(MessageHandler(filters.Regex('^آپلود لوگوی فروشگاه$'), prompt_upload_logo_handler))  # Button handler
    application.add_handler(MessageHandler(filters.Regex('^افزودن آیتم$'), add_item_handler))  # Show products

    application.add_handler(MessageHandler(filters.Regex('^افزودن مشتری$'), add_customer_handler))
    application.add_handler(MessageHandler(filters.Regex('^مشاهده مشتریان$'), view_customers))
    application.add_handler(MessageHandler(filters.Regex('^انتخاب مشتری$'), select_customer_handler))

    # Product Selection
    application.add_handler(MessageHandler(filters.Regex(r'.*\(ID:.*\)'), handle_product_selection))  

    # Quantity Input
    application.add_handler(MessageHandler(filters.Regex(r'^[Qq]\d+$'), handle_quantity_input))
    application.add_handler(MessageHandler(filters.Regex(r'^[Cc]\d+$'), save_selected_customer))
    application.add_handler(MessageHandler(filters.PHOTO, store_logo_handler))  # Photo upload handler

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, main_handler))  # Save customer info

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_store_info))  # Store information

    # Product Management Handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, add_product))          # Process Product Input

    # Invoice Management Handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_item))      # Process Item Addition




    # شروع بات
    application.run_polling()

if __name__ == '__main__':
    main()
