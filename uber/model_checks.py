"""
When an admin submits a form to create/edit an attendee/group/job/etc we usually want to perform some basic validations
on the data that was entered.  We put those validations here.  To make a validation for the Attendee model, you can
just write a function decorated with the @validation.Attendee decorator.  That function should return None on success
and an error string on failure.

In addition, you can define a set of required fields by setting the .required field like the AdminAccount.required list
below.  This should be a list of tuples where the first tuple element is the name of the field, and the second is the
name that should be displayed in the "XXX is a required field" error message.

To perform these validations, call the "check" method on the instance you're validating.  That method returns None
on success and a string error message on validation failure.
"""
from uber.common import *
from email_validator import validate_email, EmailNotValidError


AdminAccount.required = [('attendee', 'Attendee'), ('hashed', 'Password')]


@validation.AdminAccount
def duplicate_admin(account):
    if account.is_new:
        with Session() as session:
            if session.query(AdminAccount).filter_by(attendee_id=account.attendee_id).all():
                return 'That attendee already has an admin account'


@validation.AdminAccount
def has_email_address(account):
    if account.is_new:
        with Session() as session:
            if session.query(Attendee).filter_by(id=account.attendee_id).first().email == '':
                return "Attendee doesn't have a valid email set"


Group.required = [('name', 'Group Name')]


@prereg_validation.Group
def dealer_wares(group):
    if group.is_dealer and not group.wares:
        return "You must provide a detailed explanation of what you sell for us to evaluate your submission"


@prereg_validation.Group
def dealer_website(group):
    if group.is_dealer and not group.website:
        return "Please enter your business' website address"


@prereg_validation.Group
def dealer_description(group):
    if group.is_dealer and not group.description:
        return "Please provide a brief description of your business"


@prereg_validation.Group
def dealer_categories(group):
    if group.is_dealer and not group.categories:
        return "Please select at least one category your wares fall under."


@prereg_validation.Group
def dealer_other_category(group):
    if group.categories and c.OTHER in group.categories_ints and not group.categories_text:
        return "Please describe what 'other' categories your wares fall under."


@prereg_validation.Group
def dealer_address(group):
    if group.is_dealer:
        missing = []
        if not group.country:
            missing.append('country')
        if not group.address1:
            missing.append('street address')
        if not group.city:
            missing.append('city')
        if group.country == 'United States':
            if not group.region:
                missing.append('state')
            if not group.zip_code:
                missing.append('zip code')
        if group.country == 'Canada' and not group.region:
            missing.append('province or region')

        if missing:
            return 'Please provide your full address for tax purposes. ' \
                'Missing: {}'.format(', '.join(missing))


@validation.Group
def group_money(group):
    if not group.auto_recalc:
        try:
            cost = int(float(group.cost if group.cost else 0))
            if cost < 0:
                return 'Total Group Price must be a number that is 0 or higher.'
        except:
            return "What you entered for Total Group Price ({}) isn't even a number".format(group.cost)

    try:
        amount_paid = int(float(group.amount_paid if group.amount_paid else 0))
        if amount_paid < 0:
            return 'Amount Paid must be a number that is 0 or higher.'
    except:
        return "What you entered for Amount Paid ({}) isn't even a number".format(group.amount_paid)

    try:
        amount_refunded = int(float(group.amount_refunded if group.amount_refunded else 0))
        if amount_refunded < 0:
            return 'Amount Refunded must be positive'
        elif amount_refunded > amount_paid:
            return 'Amount Refunded cannot be greater than Amount Paid'
    except:
        return "What you entered for Amount Refunded ({}) wasn't even a number".format(group.amount_refunded)


def _invalid_phone_number(s):
    if not s.startswith('+'):
        return len(re.findall(r'\d', s)) != 10 or re.search(c.SAME_NUMBER_REPEATED, re.sub(r'[^0-9]', '', s))


def _invalid_zip_code(s):
    return len(re.findall(r'\d', s)) not in [5, 9]


def ignore_unassigned_and_placeholders(func):
    @wraps(func)
    def with_skipping(attendee):
        unassigned_group_reg = attendee.group_id and not attendee.first_name and not attendee.last_name
        valid_placeholder = attendee.placeholder and attendee.first_name and attendee.last_name
        if not unassigned_group_reg and not valid_placeholder:
            return func(attendee)
    return with_skipping


@prereg_validation.Attendee
def shirt_size(attendee):
    if attendee.amount_extra >= c.SHIRT_LEVEL and attendee.shirt == c.NO_SHIRT:
        return 'Your shirt size is required'


@prereg_validation.Attendee
def total_cost_over_paid(attendee):
    if attendee.total_cost < attendee.amount_paid:
        return 'You have already paid ${}, you cannot reduce your extras below that.'.format(attendee.amount_paid)


@validation.Attendee
def reasonable_total_cost(attendee):
    if attendee.total_cost >= 999999:
        return 'We cannot charge ${:,.2f}. Please reduce extras so the total is below $999,999.'.format(attendee.total_cost)


@prereg_validation.Attendee
def promo_code_is_useful(attendee):
    if attendee.promo_code:
        if not attendee.is_unpaid:
            return "You can't apply a promo code after you've paid or if you're in a group."
        elif attendee.overridden_price:
            return "You already have a special badge price, you can't use a promo code on top of that."
        elif attendee.badge_cost >= attendee.badge_cost_without_promo_code:
            return "That promo code doesn't make your badge any cheaper. " \
                "You may already have other discounts."


@prereg_validation.Attendee
def promo_code_not_is_expired(attendee):
    if attendee.promo_code and attendee.promo_code.is_expired:
        return 'That promo code is expired.'


@prereg_validation.Attendee
def promo_code_has_uses_remaining(attendee):
    if attendee.promo_code and not attendee.promo_code.is_unlimited:
        unpaid_uses_count = Charge.get_unpaid_promo_code_uses_count(
            attendee.promo_code.id, attendee.id)
        if (attendee.promo_code.uses_remaining - unpaid_uses_count) < 0:
            return 'That promo code has been used too many times.'


@validation.Attendee
@ignore_unassigned_and_placeholders
def full_name(attendee):
    if not attendee.first_name:
        return 'First Name is a required field'
    elif not attendee.last_name:
        return 'Last Name is a required field'


@validation.Attendee
def allowed_to_volunteer(attendee):
    if attendee.staffing and not attendee.age_group_conf['can_volunteer'] and attendee.badge_type != c.STAFF_BADGE and c.PRE_CON:
        return 'Your interest is appreciated, but ' + c.EVENT_NAME + ' volunteers must be 18 or older.'


@validation.Attendee
@ignore_unassigned_and_placeholders
def age(attendee):
    if c.COLLECT_EXACT_BIRTHDATE:
        if not attendee.birthdate:
            return 'Please enter a date of birth.'
        elif attendee.birthdate > date.today():
            return 'You cannot be born in the future.'
    elif not attendee.age_group:
        return 'Please enter your age group'


@validation.Attendee
def allowed_to_register(attendee):
    if not attendee.age_group_conf['can_register']:
        return 'Attendees ' + attendee.age_group_conf['desc'] + ' years of age do not need to register, but MUST be accompanied by a parent at all times!'


@validation.Attendee
@ignore_unassigned_and_placeholders
def email(attendee):
    if len(attendee.email) > 255:
        return 'Email addresses cannot be longer than 255 characters.'
    elif not attendee.email and not c.AT_OR_POST_CON:
        return 'Please enter an email address.'


@validation.Attendee
def email_valid(attendee):
    if attendee.email:
        try:
            validate_email(attendee.email)
        except EmailNotValidError as e:
            message = str(e)
            return 'Enter a valid email address. ' + message


@validation.Attendee
@ignore_unassigned_and_placeholders
def address(attendee):
    if c.COLLECT_FULL_ADDRESS:
        if not attendee.address1:
            return 'Please enter a street address.'
        if not attendee.city:
            return 'Please enter a city.'
        if not attendee.region and attendee.country in ['United States', 'Canada']:
            return 'Please enter a state, province, or region.'
        if not attendee.country:
            return 'Please enter a country.'


@validation.Attendee
@ignore_unassigned_and_placeholders
def zip_code(attendee):
    if not attendee.international and not c.AT_OR_POST_CON:
        if _invalid_zip_code(attendee.zip_code):
            return 'Enter a valid zip code'


@validation.Attendee
@ignore_unassigned_and_placeholders
def emergency_contact(attendee):
    if not attendee.ec_name:
        return 'Please tell us the name of your emergency contact.'
    if not attendee.international and _invalid_phone_number(attendee.ec_phone):
        if c.COLLECT_FULL_ADDRESS:
            return 'Enter a 10-digit US phone number or include a country code (e.g. +44) for your emergency contact number.'
        else:
            return 'Enter a 10-digit emergency contact number.'


@validation.Attendee
@ignore_unassigned_and_placeholders
def cellphone(attendee):
    if attendee.cellphone and _invalid_phone_number(attendee.cellphone):
        if c.COLLECT_FULL_ADDRESS:
            return 'Enter a 10-digit US phone number or include a country code (e.g. +44) for your phone number.'
        else:
            return 'Your phone number was not a valid 10-digit phone number'

    if not attendee.no_cellphone and attendee.staffing and not attendee.cellphone:
        return "Phone number is required for volunteers (unless you don't own a cellphone)"


@prereg_validation.Attendee
def dealer_cellphone(attendee):
    if attendee.badge_type == c.PSEUDO_DEALER_BADGE and not attendee.cellphone:
        return 'Your phone number is required'


@validation.Attendee
@ignore_unassigned_and_placeholders
def emergency_contact_not_cellphone(attendee):
    if not attendee.international and attendee.cellphone and attendee.cellphone == attendee.ec_phone:
        return "Your phone number cannot be the same as your emergency contact number"


@validation.Attendee
def printed_badge_deadline(attendee):
    if attendee.is_new and attendee.has_personalized_badge and c.AFTER_PRINTED_BADGE_DEADLINE:
        return 'Custom badges have already been ordered so you cannot create new {} badges'.format(attendee.badge_type_label)


@validation.Attendee
def printed_badge_change(attendee):
    badge_name_changes_allowed = True

    # this is getting kinda messy and we probably need to rework the entire concept of "printed badge deadline".
    # right now we want to:
    # 1) allow supporters to change their badge names until c.SUPPORTER_DEADLINE
    # 2) allow staff to change their badge names until c.PRINTED_BADGE_DEADLINE
    #
    # this implies that we actually have two different printed badge deadlines: 1 for staff, 1 for supporters.
    # we might just want to make that explicit.
    if attendee.badge_type == c.STAFF_BADGE and c.AFTER_PRINTED_BADGE_DEADLINE:
        badge_name_changes_allowed = False
    elif attendee.amount_extra >= c.SUPPORTER_LEVEL and c.AFTER_SUPPORTER_DEADLINE:
        badge_name_changes_allowed = False

    if not badge_name_changes_allowed:
        if attendee.badge_printed_name != attendee.orig_value_of('badge_printed_name'):
            return 'Custom badges have already been ordered, so you cannot change the printed name of this Attendee'


@validation.Attendee
def group_leadership(attendee):
    if attendee.session and not attendee.group_id:
        orig_group_id = attendee.orig_value_of('group_id')
        if orig_group_id and attendee.id == attendee.session.group(orig_group_id).leader_id:
            return 'You cannot remove the leader of a group from that group; make someone else the leader first'


@validation.Attendee
def banned_volunteer(attendee):
    if (c.VOLUNTEER_RIBBON in attendee.ribbon_ints or attendee.staffing) and attendee.full_name in c.BANNED_STAFFERS:
        return "We've declined to invite {} back as a volunteer, ".format(attendee.full_name) + (
                    'talk to Stops to override if necessary' if c.AT_THE_CON else
                    'Please contact us via {} if you believe this is in error'.format(c.CONTACT_URL))


@validation.Attendee
def attendee_money(attendee):
    try:
        amount_paid = int(float(attendee.amount_paid))
        if amount_paid < 0:
            return 'Amount Paid cannot be less than zero'
    except:
        return "What you entered for Amount Paid ({}) wasn't even a number".format(attendee.amount_paid)

    try:
        amount_extra = int(float(attendee.amount_extra or 0))
        if amount_extra < 0:
            return 'Amount extra must be a positive integer'
    except:
        return 'Invalid amount extra ({})'.format(attendee.amount_extra)

    if attendee.overridden_price is not None:
        try:
            overridden_price = int(float(attendee.overridden_price))
            if overridden_price < 0:
                return 'Overridden price must be a positive integer'
        except:
            return 'Invalid overridden price ({})'.format(attendee.overridden_price)

    try:
        amount_refunded = int(float(attendee.amount_refunded))
        if amount_refunded < 0:
            return 'Amount Refunded must be positive'
        elif amount_refunded > amount_paid:
            return 'Amount Refunded cannot be greater than Amount Paid'
        elif attendee.paid == c.REFUNDED and amount_refunded == 0:
            return 'Amount Refunded may not be 0 if the attendee is marked Paid and Refunded'
    except:
        return "What you entered for Amount Refunded ({}) wasn't even a number".format(attendee.amount_refunded)


@validation.Attendee
def dealer_needs_group(attendee):
    if attendee.is_dealer and not attendee.badge_type == c.PSEUDO_DEALER_BADGE and not attendee.group_id:
        return 'Dealers must be associated with a group'


@validation.Attendee
def dupe_badge_num(attendee):
    if (attendee.badge_num != attendee.orig_value_of('badge_num') or attendee.is_new)\
            and c.NUMBERED_BADGES and attendee.badge_num and\
            (not c.SHIFT_CUSTOM_BADGES or c.AFTER_PRINTED_BADGE_DEADLINE or c.AT_THE_CON):
        with Session() as session:
            existing = session.query(Attendee)\
                .filter_by(badge_type=attendee.badge_type, badge_num=attendee.badge_num)
            if existing.count():
                return 'That badge number already belongs to {!r}'.format(existing.first().full_name)


@validation.Attendee
def invalid_badge_num(attendee):
    if c.NUMBERED_BADGES and attendee.badge_num:
        try:
            badge_num = int(attendee.badge_num)
        except:
            return '{!r} is not a valid badge number'.format(attendee.badge_num)


@validation.Attendee
def no_more_custom_badges(attendee):
    if (attendee.badge_type != attendee.orig_value_of('badge_type') or attendee.is_new)\
            and attendee.has_personalized_badge and c.AFTER_PRINTED_BADGE_DEADLINE:
        return 'Custom badges have already been ordered'


@validation.Attendee
def out_of_badge_type(attendee):
    if attendee.badge_type != attendee.orig_value_of('badge_type'):
        with Session() as session:
            try:
                session.get_next_badge_num(attendee.badge_type_real)
            except AssertionError:
                return 'There are no more badges available for that type'


@validation.Attendee
def invalid_badge_name(attendee):
    if attendee.badge_printed_name and c.BEFORE_PRINTED_BADGE_DEADLINE \
            and re.search(c.INVALID_BADGE_PRINTED_CHARS, attendee.badge_printed_name):
        return 'Your printed badge name has invalid characters. Please use only printable ASCII characters.'


@validation.Attendee
def extra_donation_valid(attendee):
    try:
        extra_donation = int(float(attendee.extra_donation if attendee.extra_donation else 0))
        if extra_donation < 0:
            return 'Extra Donation must be a number that is 0 or higher.'
    except:
        return "What you entered for Extra Donation ({}) isn't even a number".format(attendee.extra_donation)


@validation.MPointsForCash
@validation.OldMPointExchange
def money_amount(model):
    if not str(model.amount).isdigit():
        return 'Amount must be a positive number'


Job.required = [('name', 'Job Name')]


@validation.Job
def slots(job):
    if job.slots < len(job.shifts):
        return 'You cannot reduce the number of slots to below the number of staffers currently signed up for this job'


@validation.Job
def time_conflicts(job):
    if not job.is_new:
        original_hours = Job(start_time=job.orig_value_of('start_time'), duration=job.orig_value_of('duration')).hours
        for shift in job.shifts:
            if job.hours.intersection(shift.attendee.hours - original_hours):
                return 'You cannot change this job to this time, because {} is already working a shift then'.format(shift.attendee.full_name)


@validation.OldMPointExchange
def oldmpointexchange_numbers(mpe):
    if not str(mpe.amount).isdigit():
        return 'MPoints must be a positive integer'


Sale.required = [('what', "What's being sold")]


@validation.Sale
def cash_and_mpoints(sale):
    if not str(sale.cash).isdigit() or int(sale.cash) < 0:
        return 'Cash must be a positive integer'
    if not str(sale.mpoints).isdigit() or int(sale.mpoints) < 0:
        return 'MPoints must be a positive integer'


PromoCode.required = [('expiration_date', 'Expiration date')]


@validation.PromoCode
def valid_discount(promo_code):
    if promo_code.discount:
        try:
            promo_code.discount = int(promo_code.discount)
            if promo_code.discount < 0:
                return 'You cannot give out promo codes that increase badge prices.'
        except:
            return "What you entered for the discount isn't even a number."


@validation.PromoCode
def valid_uses_allowed(promo_code):
    if promo_code.uses_allowed:
        try:
            promo_code.uses_allowed = int(promo_code.uses_allowed)
            if promo_code.uses_allowed < 0 or promo_code.uses_allowed < promo_code.uses_count:
                return 'Promo codes must have at least 0 uses remaining.'
        except:
            return "What you entered for the number of uses allowed isn't even a number."


@validation.PromoCode
def no_unlimited_free_badges(promo_code):
    if promo_code.is_new \
            or promo_code.uses_allowed != promo_code.orig_value_of('uses_allowed') \
            or promo_code.discount != promo_code.orig_value_of('discount') \
            or promo_code.discount_type != promo_code.orig_value_of('discount_type'):
        if promo_code.is_unlimited and promo_code.is_free:
            return 'Unlimited-use, free-badge promo codes are not allowed.'


@validation.PromoCode
def no_dupe_code(promo_code):
    if promo_code.code and (
            promo_code.is_new or
            promo_code.code != promo_code.orig_value_of('code')):
        with Session() as session:
            if session.lookup_promo_code(promo_code.code):
                return 'The code you entered already belongs to another ' \
                    'promo code. Note that promo codes are not case sensitive.'
