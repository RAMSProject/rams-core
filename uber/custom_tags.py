"""
Portions of this file are copied from the Django project. Relevant portions are
Copyright (c) Django Software Foundation and individual contributors.
Licensed under BSD license, see full license for details:
https://github.com/django/django/blob/4696078832f486ba63f0783a0795294b3d80d862/LICENSE
"""

from dateutil.relativedelta import relativedelta
from uber.common import *
from sideboard.lib.sa import _camelcase_to_underscore as uncamel, \
    _underscore_to_camelcase as camel


def safe_string(text):
    if isinstance(text, Markup):
        return text
    else:
        return Markup(text)


@JinjaEnv.jinja_filter
def basename(s):
    return os.path.basename(s) if s else ''


@JinjaEnv.jinja_test(name='class')
def is_class(value):
    return inspect.isclass(value)


@JinjaEnv.jinja_filter
def fieldify(s):
    return re.sub(r'[\W_]+', '_', uncamel(s)).strip('_')


@JinjaEnv.jinja_filter
def unfieldify(s):
    return (' '.join([s for s in s.strip('_ ').split('_') if s])).title()


@JinjaEnv.jinja_filter(name='datetime')
def datetime_filter(dt, fmt='%-I:%M%p %Z on %A, %b %-e'):
    return '' if not dt else ' '.join(dt.strftime(fmt).split()).replace('AM', 'am').replace('PM', 'pm')


@JinjaEnv.jinja_filter(name='datetime_local')
def datetime_local_filter(dt, fmt='%-I:%M%p %Z on %A, %b %-e'):
    return '' if not dt else datetime_filter(dt.astimezone(c.EVENT_TIMEZONE), fmt=fmt)


@JinjaEnv.jinja_filter
def time_day_local(dt):
    if not dt:
        return ''
    dt_local = dt.astimezone(c.EVENT_TIMEZONE)
    time_str = dt_local.strftime('%-I:%M%p').lstrip('0').lower()
    day_str = dt_local.strftime('%a')
    return safe_string('<nobr>{} {}</nobr>'.format(time_str, day_str))


@JinjaEnv.jinja_filter(name='timedelta')
def timedelta_filter(dt, *args, **kwargs):
    """Returns a datetime object offset by a timedelta specified by the given arguments.

    Takes the same arguments as the standard library's datetime.timedelta class.
    Returns None if an empty datetime object is given.
    """
    if not dt:
        return None
    return dt + timedelta(*args, **kwargs)


@JinjaEnv.jinja_filter
def full_datetime_local(dt):
    return '' if not dt else dt.astimezone(c.EVENT_TIMEZONE).strftime('%H:%M on %B %d %Y')


@JinjaEnv.jinja_export
def event_dates():
    if c.EPOCH.date() == c.ESCHATON.date():
        return c.EPOCH.strftime('%B %-d')
    elif c.EPOCH.month != c.ESCHATON.month:
        return '{} - {}'.format(c.EPOCH.strftime('%B %-d'), c.ESCHATON.strftime('%B %-d'))
    else:
        return '{}-{}'.format(c.EPOCH.strftime('%B %-d'), c.ESCHATON.strftime('%-d'))


@JinjaEnv.jinja_export
def hour_day_local(dt):
    # NOTE: hour_day_format() already localizes the given datetime object
    return '' if not dt else hour_day_format(dt)


@JinjaEnv.jinja_filter
def timestamp(dt):
    from time import mktime
    return '' if not dt else str(int(mktime(dt.timetuple())))


@JinjaEnv.jinja_filter
def yesno(value, arg=None):
    """
    PORTED FROM DJANGO

    Given a string mapping values for true, false and (optionally) None,
    returns one of those strings according to the value:

    ==========  ======================  ==================================
    Value       Argument                Outputs
    ==========  ======================  ==================================
    ``True``    ``"yeah,no,maybe"``     ``yeah``
    ``False``   ``"yeah,no,maybe"``     ``no``
    ``None``    ``"yeah,no,maybe"``     ``maybe``
    ``None``    ``"yeah,no"``           ``"no"`` (converts None to False
                                        if no mapping for None is given.
    ==========  ======================  ==================================
    """
    if arg is None:
        arg = 'yes,no,maybe'
    bits = arg.split(',')
    if len(bits) < 2:
        return value  # Invalid arg.
    try:
        yes, no, maybe = bits
    except ValueError:
        # Unpack list of wrong size (no "maybe" value provided).
        yes, no, maybe = bits[0], bits[1], bits[1]
    if value is None:
        return maybe
    if value:
        return yes
    return no


@JinjaEnv.jinja_filter
def jsonize(x):
    is_empty = x is None or isinstance(x, jinja2.runtime.Undefined)
    return safe_string('{}' if is_empty else html.escape(json.dumps(x, cls=serializer), quote=False))


@JinjaEnv.jinja_filter
def subtract(x, y):
    return x - y


@JinjaEnv.jinja_filter
def urlencode(s):
    if isinstance(s, Markup):
        s = s.unescape()
    s = quote_plus(s.encode('utf8'))
    return Markup(s)


@JinjaEnv.jinja_filter
def url_to_link(url=None, text=None, target=None, is_relative=True):
    # Jinja2 has a 'urlize' filter but it depends on links having `.com` or
    # `http` in the name. This works with relative links and allows you to
    # also define link text.
    if not url:
        return ''

    if not text:
        text = url

    if not is_relative and not url.startswith('http'):
        url = 'http://' + url

    return safe_string('<a href="{}"{}>{}</a>'.format(
        jinja2.escape(url),
        ' target="{}"'.format(jinja2.escape(target)) if target else '',
        jinja2.escape(text)))


@JinjaEnv.jinja_filter
def email_to_link(email=None):
    """
    Creates an <a href="mailto:email@example.com">email@example.com</a> link.
    """
    if not email:
        return ''

    return safe_string('<a href="mailto:{0}">{0}</a>'.format(jinja2.escape(email)))


@JinjaEnv.jinja_filter
def percent(numerator, denominator):
    return '0/0' if denominator == 0 else '{} / {} ({}%)'.format(numerator, denominator, int(100 * numerator / denominator))


@JinjaEnv.jinja_filter
def percent_of(numerator, denominator):
    return 'n/a' if denominator == 0 else '{}%'.format(int(100 * numerator / denominator))


@JinjaEnv.jinja_filter
def remove_newlines(string):
    return string.replace('\n', ' ')


@JinjaEnv.jinja_filter
def form_link(model):
    if isinstance(model, uber.models.Attendee):
        return safe_string('<a href="../registration/form?id={}">{}</a>'.format(model.id, jinja2.escape(model.full_name)))
    elif isinstance(model, uber.models.Group):
        return safe_string('<a href="../groups/form?id={}">{}</a>'.format(model.id, jinja2.escape(model.name)))
    elif isinstance(model, uber.models.Job):
        return safe_string('<a href="../jobs/form?id={}">{}</a>'.format(model.id, jinja2.escape(model.name)))
    elif hasattr(model, 'name'):
        return model.name
    elif hasattr(model, 'full_name'):
        return model.full_name
    else:
        return repr(model)


@JinjaEnv.jinja_filter
def dept_checklist_path(conf, attendee=None):
    return safe_string(conf.path(attendee))


@JinjaEnv.jinja_filter
def numeric_range(count):
    return range(count)


@JinjaEnv.jinja_filter
def sum(values, attribute):
    sum = 0
    for value in values:
        sum += getattr(value, attribute, 0)
    return sum


def _getter(x, attrName):
    if '.' in attrName:
        first, rest = attrName.split('.', 1)
        return _getter(getattr(x, first), rest)
    else:
        return getattr(x, attrName)


@JinjaEnv.jinja_filter
def sortBy(xs, attrName):
    return sorted(xs, key=lambda x: _getter(x, attrName))


@JinjaEnv.jinja_filter
def idize(s):
    return re.sub('\W+', '_', str(s)).strip('_')


@JinjaEnv.jinja_filter
def pluralize(number, singular='', plural='s'):
    if number == 1:
        return singular
    else:
        return plural


@JinjaEnv.jinja_filter
def maybe_red(amount, comp):
    if amount >= comp:
        return safe_string('<span style="color:red ; font-weight:bold">{}</span>'.format(jinja2.escape(amount)))
    else:
        return amount


@JinjaEnv.jinja_filter
def maybe_last_year(day):
    return 'last year' if day <= c.STAFFERS_IMPORTED else day


@JinjaEnv.jinja_filter
def join_and(xs):
    if len(xs) in [0, 1, 2]:
        return ' and '.join(xs)
    else:
        xs = xs[:-1] + ['and ' + xs[-1]]
        return ', '.join(xs)


@JinjaEnv.jinja_filter
def email_only(email):
    """
    Our configured email addresses support either the "email@domain.com" format
    or the longer "Email Name <email@domain.com>" format.  We generally want the
    former to be used in our text-only emails.  This filter takes an email which
    can be in either format and spits out just the email address portion.
    """
    return re.search(c.EMAIL_RE.lstrip('^').rstrip('$'), email).group()


@JinjaEnv.jinja_export
def humanize_timedelta(*args, granularity='seconds', **kwargs):
    """
    Converts a time interval into a nicely formatted human readable string.

    Accepts either a single `datetime.timedelta` instance, or a series of
    keyword arguments specifying time units:

      - years
      - months
      - days
      - hours
      - minutes
      - seconds

    Args:
        delta (datetime.timedelta): The timedelta to format
        granularity (str): The smallest unit of time that should be included.
            Defaults to "seconds".
        years (int, float): A number of years.
        months (int, float): A number of months.
        days (int, float): A number of days.
        hours (int, float): A number of hours.
        minutes (int, float): A number of minutes.
        seconds (int, float): A number of seconds.

    Returns:
        str: A human readable string, like "2 hours and 45 minutes", or
            "right now" if the timedelta is equal to zero.
    """
    if args and isinstance(args[0], timedelta):
        delta = relativedelta(seconds=args[0].total_seconds()).normalized()
    else:
        delta = relativedelta(**kwargs).normalized()
    units = ['years', 'months', 'days', 'hours', 'minutes', 'seconds']
    time_units = []
    for unit in units:
        time = abs(int(getattr(delta, unit)))
        if time:
            plural = pluralize(time)
            time_units.append('{} {}{}'.format(time, unit[:-1], plural))
        if unit == granularity:
            break
    if time_units:
        return join_and(time_units)
    else:
        return 'right now'


@JinjaEnv.jinja_export
def options(options, default='""'):
    """
    We do need to accomodate explicitly passing in other options though
    (include None), so make sure to check all the client calls for that info.
    """
    if isinstance(default, datetime):
        default = default.astimezone(c.EVENT_TIMEZONE)

    results = []
    for opt in options:
        if len(listify(opt)) == 1:
            opt = [opt, opt]
        val, desc = opt
        if isinstance(val, datetime):
            selected = 'selected="selected"' if val == default else ''
            val = val.strftime(c.TIMESTAMP_FORMAT)
        else:
            selected = 'selected="selected"' if str(val) == str(default) else ''
        val  = html.escape(str(val), quote=False).replace('"',  '&quot;').replace('\n', '')
        desc = html.escape(str(desc), quote=False).replace('"', '&quot;').replace('\n', '')
        results.append('<option value="{}" {}>{}</option>'.format(val, selected, desc))
    return safe_string('\n'.join(results))


@JinjaEnv.jinja_export
def int_options(minval, maxval, default=1):
    results = []
    default = str(default)
    for i in range(minval, maxval+1):
        selected = 'selected="selected"' if str(i) == default else ''
        results.append('<option value="{val}" {selected}>{val}</option>'.format(val=i, selected=selected))
    return safe_string('\n'.join(results))


@JinjaEnv.jinja_export
def pages(page, count):
    page = int(page)
    pages = []
    for pagenum in range(1, int(math.ceil(count / 100)) + 1):
        if pagenum == page:
            pages.append('<li class="page-item active"><a class="page-link" href="#">{}</a></li>'.format(pagenum))
        else:
            path = cherrypy.request.request_line.split()[1].split('/')[-1]
            page_qs = 'page={}'.format(pagenum)
            if 'page=' in path:
                path = re.sub(r'page=\d+', page_qs, path)
            else:
                path += ('&' if '?' in path else '?') + page_qs
            pages.append('<li class="page-item"><a class="page-link" href="{}">{}</a></li>'.format(path, pagenum))
    return safe_string('<ul class="pagination">' + ' '.join(map(str, pages)) + '</ul>')


def extract_fields(what):
    if isinstance(what, Attendee):
        return 'a{}'.format(what.id), what.full_name, what.total_cost
    elif isinstance(what, Group):
        return 'g{}'.format(what.id), what.name, what.amount_unpaid
    else:
        return None, None, None


@JinjaEnv.jinja_filter
def linebreaksbr(text):
    """Convert all newlines ("\n") in a string to HTML line breaks ("<br />")"""
    is_markup = isinstance(text, Markup)
    text = normalize_newlines(text)
    if not is_markup:
        text = text_type(jinja2.escape(text))
    text = text.replace('\n', '<br />')
    return safe_string(text)


def normalize_newlines(text):
    if text:
        return re.sub(r'\r\n|\r|\n', '\n', str(text))
    else:
        return ''


@JinjaEnv.jinja_export
def csrf_token():
    if not cherrypy.session.get('csrf_token'):
        cherrypy.session['csrf_token'] = uuid4().hex
    return safe_string('<input type="hidden" name="csrf_token" value="{}" />'.format(cherrypy.session["csrf_token"]))


@JinjaEnv.jinja_export
def stripe_form(action, charge):
    payment_id = uuid4().hex
    cherrypy.session[payment_id] = charge.to_dict()

    email = None
    if charge.models and charge.models[0].email:
        email = charge.models[0].email[:255]

    if not charge.models:
        if c.AT_THE_CON:
            regtext = 'On-Site Charge'
        else:
            regtext = 'Charge'
    elif c.AT_THE_CON:
        regtext = 'Registration'
    else:
        regtext = 'Preregistration'

    params = {
        'action': action,
        'regtext': regtext,
        'email': email,
        'payment_id': payment_id,
        'charge': charge
    }

    return safe_string(render('preregistration/stripeForm.html', params).decode('utf-8'))


@JinjaEnv.jinja_export
def organization_with_event_name(separator='and'):
    if c.EVENT_NAME.lower() != c.ORGANIZATION_NAME.lower():
        return '{} {} {}'.format(c.EVENT_NAME, separator.strip(), c.ORGANIZATION_NAME)
    else:
        return c.EVENT_NAME


@JinjaEnv.jinja_export
def single_day_prices():
    prices = ''
    for day, price in c.BADGE_PRICES['single_day'].items():
        if day == datetime.strftime(c.ESCHATON, "%A"):
            prices += 'and ${} for {}'.format(price, day)
            break
        else:
            prices += '${} for {}, '.format(price, day)
    return prices


@JinjaEnv.jinja_export
def price_notice(label, takedown, amount_extra=0, discount=0):
    if c.HARDCORE_OPTIMIZATIONS_ENABLED:
        # CPU optimizaiton: the calculations done in this function are somewhat expensive and even with caching,
        # still do some expensive DB queries.  if hardcore optimizations mode is enabled, we display a
        # simpler message.  This is intended to be enabled during the heaviest loads at the beginning of an event
        # in order to reduce server load so the system stays up.  After the rush, it should be safe to turn this
        # back off
        return ''

    if not takedown:
        takedown = c.ESCHATON

    if c.PAGE_PATH not in ['/preregistration/form', '/preregistration/post_form', '/preregistration/register_group_member']:
        return ''  # we only display notices for new attendees
    else:
        badge_price = c.BADGE_PRICE  # optimization.  this call is VERY EXPENSIVE.
        on_or_by = "no later than" if c.PRICE_LIMITS else "on"

        for day, price in sorted(c.PRICE_BUMPS.items()):
            if day < takedown and localized_now() < day and price > badge_price:
                return safe_string('<div class="prereg-price-notice">Price goes up to ${} {} 11:59pm {} on {}</div>'.format(price - int(discount) + int(amount_extra), on_or_by, (day - timedelta(days=1)).strftime('%Z'), (day - timedelta(days=1)).strftime('%A, %b %e')))
            elif localized_now() < day and takedown == c.PREREG_TAKEDOWN and takedown < c.EPOCH and price > badge_price:
                return safe_string('<div class="prereg-type-closing">{} closes at 11:59pm {} on {}. Price goes up to ${} at-door.</div>'.format(label, takedown.strftime('%Z'), takedown.strftime('%A, %b %e'), price + amount_extra, (day - timedelta(days=1)).strftime('%A, %b %e')))
        if takedown < c.EPOCH:
            return safe_string('<div class="prereg-type-closing">{} closes at 11:59pm {} on {}</div>'.format(jinja2.escape(label), takedown.strftime('%Z'), takedown.strftime('%A, %b %e')))
        else:
            return ''


@JinjaEnv.jinja_export
def table_prices():
    if len(c.TABLE_PRICES) <= 1:
        return '${} per table'.format(c.TABLE_PRICES['default_price'])
    else:
        cost, costs = 0, []
        for i in range(1, 1 + c.MAX_TABLES):
            cost += c.TABLE_PRICES[i]
            table_plural, cost_plural = ('', 's') if i == 1 else ('s', '')
            costs.append('<nobr>{} table{} cost{} ${}</nobr>'.format(i, table_plural, cost_plural, cost))
        costs[-1] = 'and ' + costs[-1]
        return safe_string(', '.join(costs))


@JinjaEnv.jinja_export
def random_hash():
    random = os.urandom(16)
    result = binascii.hexlify(random)
    return result.decode("utf-8")
