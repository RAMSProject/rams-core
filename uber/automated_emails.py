# WARNING - changing the email subject line for an email causes ALL of those emails to be re-sent!
# Note that since c.EVENT_NAME is used in most of these emails, changing the event name mid-year
# could cause literally thousands of emails to be re-sent!

from uber.common import *


class AutomatedEmail:
    instances = OrderedDict()

    queries = {
        Attendee: lambda session: session.staffers(only_staffing=False),
        Group: lambda session: session.query(Group).options(subqueryload(Group.attendees))
    }
    extra_models = queries  # we've renamed "extra_models" to "queries" but are temporarily keeping the old name for backwards-compatibility

    def __init__(self, model, subject, template, filter, *, sender=None, extra_data=None, cc=None, bcc=None, post_con=False, needs_approval=True):
        self.model, self.template, self.needs_approval = model, template, needs_approval
        self.subject = subject.format(EVENT_NAME=c.EVENT_NAME)
        self.cc = cc or []
        self.bcc = bcc or []
        self.extra_data = extra_data or {}
        self.sender = sender or c.REGDESK_EMAIL
        self.instances[self.subject] = self
        if post_con:
            self.filter = lambda x: c.POST_CON and filter(x)
        else:
            self.filter = lambda x: not c.POST_CON and filter(x)

    def __repr__(self):
        return '<{}: {!r}>'.format(self.__class__.__name__, self.subject)

    def prev(self, x, all_sent=None):
        if all_sent:
            return (x.__class__.__name__, x.id, self.subject) in all_sent
        else:
            with Session() as session:
                return session.query(Email).filter_by(model=x.__class__.__name__, fk_id=x.id, subject=self.subject).first()

    def should_send(self, x, all_sent=None):
        try:
            return x.email and not self.prev(x, all_sent) and self.filter(x)
        except:
            log.error('unexpected error', exc_info=True)

    def render(self, x):
        model = getattr(x, 'email_model_name', x.__class__.__name__.lower())
        return render('emails/' + self.template, dict({model: x}, **self.extra_data))

    def send(self, x, raise_errors=True):
        try:
            format = 'text' if self.template.endswith('.txt') else 'html'
            send_email(self.sender, x.email, self.subject, self.render(x), format, model=x, cc=self.cc)
        except:
            log.error('error sending {!r} email to {}', self.subject, x.email, exc_info=True)
            if raise_errors:
                raise

    @classmethod
    def send_all(cls, raise_errors=False):
        if not c.AT_THE_CON and (c.DEV_BOX or c.SEND_EMAILS):
            with Session() as session:
                approved = {ae.subject for ae in session.query(ApprovedEmail)}
                all_sent = set(session.query(Email.model, Email.fk_id, Email.subject))
                for model, lister in cls.queries.items():
                    for inst in lister(session):
                        sleep(0.01)  # throttle CPU usage
                        for rem in cls.instances.values():
                            if isinstance(inst, rem.model) and (not rem.needs_approval or rem.subject in approved):
                                if rem.should_send(inst, all_sent):
                                    rem.send(inst, raise_errors=raise_errors)


class StopsEmail(AutomatedEmail):
    def __init__(self, subject, template, filter, **kwargs):
        AutomatedEmail.__init__(self, Attendee, subject, template, lambda a: a.staffing and filter(a), sender=c.STAFF_EMAIL, **kwargs)


class GuestEmail(AutomatedEmail):
    def __init__(self, subject, template, filter=lambda a: True, **kwargs):
        AutomatedEmail.__init__(self, Attendee, subject, template, lambda a: a.badge_type == c.GUEST_BADGE and filter(a), sender=c.PANELS_EMAIL, **kwargs)


class GroupEmail(AutomatedEmail):
    def __init__(self, subject, template, filter, **kwargs):
        AutomatedEmail.__init__(self, Group, subject, template, lambda g: not g.is_dealer and filter(g), sender=c.REGDESK_EMAIL, **kwargs)


class MarketplaceEmail(AutomatedEmail):
    def __init__(self, subject, template, filter, **kwargs):
        AutomatedEmail.__init__(self, Group, subject, template, lambda g: g.is_dealer and filter(g), sender=c.MARKETPLACE_EMAIL, **kwargs)


class DeptChecklistEmail(AutomatedEmail):
    def __init__(self, conf):
        AutomatedEmail.__init__(self, Attendee,
                                subject='{EVENT_NAME} Department Checklist: ' + conf.name,
                                template='shifts/dept_checklist.txt',
                                filter=lambda a: a.is_single_dept_head and a.admin_account and days_before(7, conf.deadline) and not conf.completed(a),
                                sender=c.STAFF_EMAIL,
                                extra_data={'conf': conf})

before = lambda dt: bool(dt) and localized_now() < dt
after = lambda dt: bool(dt) and localized_now() > dt
days_after = lambda days, dt: bool(dt) and (localized_now() > dt + timedelta(days=days))


def days_before(days, dt, until=None):
    if dt:
        until = (dt - timedelta(days=until)) if until else dt
        return dt - timedelta(days=days) < localized_now() < until
    else:
        return None


# Payment reminder emails, including ones for groups, which are always safe to be here, since they just
# won't get sent if group registration is turned off.

AutomatedEmail(Attendee, '{EVENT_NAME} payment received', 'reg_workflow/attendee_confirmation.html',
         lambda a: a.paid == c.HAS_PAID,
         needs_approval=False)

AutomatedEmail(Group, '{EVENT_NAME} group payment received', 'reg_workflow/group_confirmation.html',
         lambda g: g.amount_paid == g.cost and g.cost != 0,
         needs_approval=False)

AutomatedEmail(Attendee, '{EVENT_NAME} group registration confirmed', 'reg_workflow/attendee_confirmation.html',
         lambda a: a.group and a != a.group.leader and not a.placeholder,
         needs_approval=False)

AutomatedEmail(Attendee, '{EVENT_NAME} extra payment received', 'reg_workflow/group_donation.txt',
         lambda a: a.paid == c.PAID_BY_GROUP and a.amount_extra and a.amount_paid == a.amount_extra,
         needs_approval=False)

AutomatedEmail(Attendee, '{EVENT_NAME} payment refunded', 'reg_workflow/payment_refunded.txt',
         lambda a: a.amount_refunded)

# Reminder emails for groups to allocated their unassigned badges.  These emails are safe to be turned on for
# all events, because they will only be sent for groups with unregistered badges, so if group preregistration
# has been turned off, they'll just never be sent.

GroupEmail('Reminder to pre-assign {EVENT_NAME} group badges', 'reg_workflow/group_preassign_reminder.txt',
           lambda g: days_after(30, g.registered) and c.BEFORE_GROUP_PREREG_TAKEDOWN and g.unregistered_badges,
           needs_approval=False)

AutomatedEmail(Group, 'Last chance to pre-assign {EVENT_NAME} group badges', 'reg_workflow/group_preassign_reminder.txt',
         lambda g: c.AFTER_GROUP_PREREG_TAKEDOWN and g.unregistered_badges and (not g.is_dealer or g.status == c.APPROVED),
         needs_approval=False)


# Dealer emails; these are safe to be turned on for all events because even if the event doesn't have dealers,
# none of these emails will be sent unless someone has applied to be a dealer, which they cannot do until
# dealer registration has been turned on.

MarketplaceEmail('Your {EVENT_NAME} Dealer registration has been approved', 'dealers/approved.html',
                 lambda g: g.status == c.APPROVED,
                 needs_approval=False)

MarketplaceEmail('Reminder to pay for your {EVENT_NAME} Dealer registration', 'dealers/payment_reminder.txt',
                 lambda g: g.status == c.APPROVED and days_after(30, g.approved) and g.is_unpaid and c.DEALER_PAYMENT_DUE,
                 needs_approval=False)

MarketplaceEmail('Your {EVENT_NAME} Dealer registration is due in one week', 'dealers/payment_reminder.txt',
                 lambda g: g.status == c.APPROVED and days_before(7, c.DEALER_PAYMENT_DUE, 2) and g.is_unpaid,
                 needs_approval=False)

MarketplaceEmail('Last chance to pay for your {EVENT_NAME} Dealer registration', 'dealers/payment_reminder.txt',
                 lambda g: g.status == c.APPROVED and days_before(2, c.DEALER_PAYMENT_DUE) and g.is_unpaid,
                 needs_approval=False)

MarketplaceEmail('{EVENT_NAME} Dealer waitlist has been exhausted', 'dealers/waitlist_closing.txt',
                 lambda g: c.AFTER_DEALER_WAITLIST_CLOSED and g.status == c.WAITLISTED)


# Placeholder badge emails; when an admin creates a "placeholder" badge, we send one of three different emails depending
# on whether the placeholder is a regular attendee, a guest/panelist, or a volunteer/staffer.  We also send a final
# reminder email before the placeholder deadline explaining that the badge must be explicitly accepted or we'll assume
# the person isn't coming.
#
# We usually import a bunch of last year's staffers before preregistration goes live with placeholder badges, so there's
# a special email for those people, which is basically the same as the normal email except it includes a special thanks
# message.  We identify those people by checking for volunteer placeholders which were created before prereg opens.
#
# These emails are safe to be turned on for all events because none of them are sent unless an administrator explicitly
# creates a "placeholder" registration.

AutomatedEmail(Attendee, '{EVENT_NAME} Panelist Badge Confirmation', 'placeholders/panelist.txt',
               lambda a: a.placeholder and a.first_name and a.last_name and a.ribbon == c.PANELIST_RIBBON,
               sender=c.PANELS_EMAIL)

AutomatedEmail(Attendee, '{EVENT_NAME} Guest Badge Confirmation', 'placeholders/guest.txt',
               lambda a: a.placeholder and a.first_name and a.last_name and a.badge_type == c.GUEST_BADGE,
               sender=c.PANELS_EMAIL)

AutomatedEmail(Attendee, '{EVENT_NAME} Dealer Information Required', 'placeholders/dealer.txt',
               lambda a: a.placeholder and a.is_dealer and a.group.status == c.APPROVED,
               sender=c.MARKETPLACE_EMAIL)

StopsEmail('Want to staff {EVENT_NAME} again?', 'placeholders/imported_volunteer.txt',
           lambda a: a.placeholder and a.staffing and a.registered_local <= c.PREREG_OPEN)

StopsEmail('{EVENT_NAME} Volunteer Badge Confirmation', 'placeholders/volunteer.txt',
           lambda a: a.placeholder and a.first_name and a.last_name
                                      and a.registered_local > c.PREREG_OPEN)

AutomatedEmail(Attendee, '{EVENT_NAME} Badge Confirmation', 'placeholders/regular.txt',
               lambda a: a.placeholder and a.first_name and a.last_name
                                       and a.badge_type not in [c.GUEST_BADGE, c.STAFF_BADGE]
                                       and a.ribbon not in [c.DEALER_RIBBON, c.PANELIST_RIBBON, c.VOLUNTEER_RIBBON])

AutomatedEmail(Attendee, '{EVENT_NAME} Badge Confirmation Reminder', 'placeholders/reminder.txt',
               lambda a: days_after(7, a.registered) and a.placeholder and a.first_name and a.last_name and not a.is_dealer)

AutomatedEmail(Attendee, 'Last Chance to Accept Your {EVENT_NAME} Badge', 'placeholders/reminder.txt',
               lambda a: days_before(7, c.PLACEHOLDER_DEADLINE) and a.placeholder and a.first_name and a.last_name
                                                                and not a.is_dealer)


# Volunteer emails; none of these will be sent unless SHIFTS_CREATED is set.

StopsEmail('{EVENT_NAME} shifts available', 'shifts/created.txt',
           lambda a: c.AFTER_SHIFTS_CREATED and a.takes_shifts)

StopsEmail('Reminder to sign up for {EVENT_NAME} shifts', 'shifts/reminder.txt',
           lambda a: c.AFTER_SHIFTS_CREATED and days_after(30, max(a.registered_local, c.SHIFTS_CREATED))
                 and c.BEFORE_PREREG_TAKEDOWN and a.takes_shifts and not a.hours)

StopsEmail('Last chance to sign up for {EVENT_NAME} shifts', 'shifts/reminder.txt',
              lambda a: days_before(10, c.EPOCH) and c.AFTER_SHIFTS_CREATED and c.BEFORE_PREREG_TAKEDOWN
                                                 and a.takes_shifts and not a.hours)

StopsEmail('Still want to volunteer at {EVENT_NAME}?', 'shifts/volunteer_check.txt',
              lambda a: c.SHIFTS_CREATED and days_before(5, c.UBER_TAKEDOWN)
                                         and a.ribbon == c.VOLUNTEER_RIBBON and a.takes_shifts and a.weighted_hours == 0)

StopsEmail('Your {EVENT_NAME} shift schedule', 'shifts/schedule.html',
           lambda a: c.SHIFTS_CREATED and days_before(1, c.UBER_TAKEDOWN) and a.weighted_hours)


# For events with customized badges, these emails remind people to let us know what we want on their badges.  We have
# one email for our volunteers who haven't bothered to confirm they're coming yet (bleh) and one for everyone else.

StopsEmail('Last chance to personalize your {EVENT_NAME} badge', 'personalized_badges/volunteers.txt',
           lambda a: days_before(7, c.PRINTED_BADGE_DEADLINE) and a.staffing and a.badge_type in c.PREASSIGNED_BADGE_TYPES and a.placeholder)

AutomatedEmail(Attendee, 'Personalized {EVENT_NAME} badges will be ordered next week', 'personalized_badges/reminder.txt',
               lambda a: days_before(7, c.PRINTED_BADGE_DEADLINE) and a.badge_type in c.PREASSIGNED_BADGE_TYPES and not a.placeholder)


# MAGFest requires signed and notarized parental consent forms for anyone under 18.  This automated email reminder to
# bring the consent form only happens if this feature is turned on by setting the CONSENT_FORM_URL config option.
AutomatedEmail(Attendee, '{EVENT_NAME} parental consent form reminder', 'reg_workflow/under_18_reminder.txt',
               lambda a: c.CONSENT_FORM_URL and a.age_group_conf['consent_form'] and days_before(14, c.EPOCH))


for _conf in DeptChecklistConf.instances.values():
    DeptChecklistEmail(_conf)
