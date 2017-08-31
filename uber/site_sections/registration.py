from uber.common import *


def pre_checkin_check(attendee, group):
    if c.NUMBERED_BADGES and not attendee.badge_num:
        return 'Badge number is required'

    if c.COLLECT_EXACT_BIRTHDATE:
        if not attendee.birthdate:
            return 'You may not check someone in without a valid date of birth.'
    elif not attendee.age_group or attendee.age_group == c.AGE_UNKNOWN:
        return 'You may not check someone in without confirming their age.'

    if attendee.checked_in:
        return attendee.full_name + ' was already checked in!'

    if group and attendee.paid == c.PAID_BY_GROUP and group.amount_unpaid:
        return 'This attendee\'s group has an outstanding balance of ${}'.format(group.amount_unpaid)

    if attendee.paid == c.NOT_PAID:
        return 'You cannot check in an attendee that has not paid.'

    return check(attendee)


def check_atd(func):
    @wraps(func)
    def checking_at_the_door(self, *args, **kwargs):
        if c.AT_THE_CON or c.DEV_BOX:
            return func(self, *args, **kwargs)
        else:
            raise HTTPRedirect('index')
    return checking_at_the_door


@all_renderable(c.PEOPLE, c.REG_AT_CON)
class Root:
    def index(self, session, message='', page='0', search_text='', uploaded_id='', order='last_first', invalid=''):
        # DEVELOPMENT ONLY: it's an extremely convenient shortcut to show the first page
        # of search results when doing testing. it's too slow in production to do this by
        # default due to the possibility of large amounts of reg stations accessing this
        # page at once. viewing the first page is also rarely useful in production when
        # there are thousands of attendees.
        if c.DEV_BOX and not int(page):
            page = 1

        filter = Attendee.badge_status.in_([c.NEW_STATUS, c.COMPLETED_STATUS]) if not invalid else None
        attendees = session.query(Attendee) if invalid else session.query(Attendee).filter(filter)
        total_count = attendees.count()
        count = 0
        search_text = search_text.strip()
        if search_text:
            attendees = session.search(search_text) if invalid else session.search(search_text, filter)
            count = attendees.count()
        if not count:
            attendees = attendees.options(joinedload(Attendee.group))
            count = total_count

        attendees = attendees.order(order)

        page = int(page)
        if search_text:
            page = page or 1
            if search_text and count == total_count:
                message = 'No matches found'
            elif search_text and count == 1 and (not c.AT_THE_CON or search_text.isdigit()):
                raise HTTPRedirect('form?id={}&message={}', attendees.one().id, 'This attendee was the only search result')

        pages = range(1, int(math.ceil(count / 100)) + 1)
        attendees = attendees[-100 + 100*page: 100*page] if page else []

        return {
            'message':        message if isinstance(message, str) else message[-1],
            'page':           page,
            'pages':          pages,
            'invalid':        invalid,
            'search_text':    search_text,
            'search_results': bool(search_text),
            'attendees':      attendees,
            'order':          Order(order),
            'attendee_count': total_count,
            'checkin_count':  session.query(Attendee).filter(Attendee.checked_in != None).count(),
            'attendee':       session.attendee(uploaded_id, allow_invalid=True) if uploaded_id else None
        }

    @log_pageview
    def form(self, session, message='', return_to='', omit_badge='', check_in='', **params):
        attendee = session.attendee(params, checkgroups=Attendee.all_checkgroups, bools=Attendee.all_bools, allow_invalid=True)
        if 'first_name' in params:
            attendee.group_id = params['group_opt'] or None
            if (c.AT_THE_CON and omit_badge) or not attendee.badge_num:
                attendee.badge_num = None

            if 'no_override' in params:
                attendee.overridden_price = None

            message = ''
            if c.BADGE_PROMO_CODES_ENABLED and 'promo_code' in params:
                message = session.add_promo_code_to_attendee(
                    attendee, params.get('promo_code'))

            if not message:
                message = check(attendee)

            if not message:
                # Free group badges are only considered 'registered' when they are actually claimed.
                if attendee.paid == c.PAID_BY_GROUP and attendee.group_id and attendee.group.cost == 0:
                    attendee.registered = localized_now()
                if check_in:
                    attendee.checked_in = localized_now()
                session.add(attendee)

                if attendee.is_new and \
                        session.attendees_with_badges().filter_by(first_name=attendee.first_name,
                                                                  last_name=attendee.last_name,
                                                                  email=attendee.email).count():
                    raise HTTPRedirect('duplicate?id={}&return_to={}', attendee.id, return_to or 'index')

                msg_text = '{} has been saved'.format(attendee.full_name)
                if params.get('save') == 'save_return_to_search':
                    if return_to:
                        raise HTTPRedirect(return_to + '&message={}', 'Attendee data saved')
                    else:
                        raise HTTPRedirect('index?uploaded_id={}&message={}&search_text={}', attendee.id, msg_text,
                            '{} {}'.format(attendee.first_name, attendee.last_name) if c.AT_THE_CON else '')
                else:
                    raise HTTPRedirect('form?id={}&message={}&return_to={}', attendee.id, msg_text, return_to)

        return {
            'message':    message,
            'attendee':   attendee,
            'check_in':   check_in,
            'return_to':  return_to,
            'omit_badge': omit_badge,
            'group_opts': [(g.id, g.name) for g in session.query(Group).order_by(Group.name).all()],
            'unassigned': {group_id: unassigned
                           for group_id, unassigned in session.query(Attendee.group_id, func.count('*'))
                                                              .filter(Attendee.group_id != None, Attendee.first_name == '')
                                                              .group_by(Attendee.group_id).all()}
        }

    def change_badge(self, session, id, message='', **params):
        attendee = session.attendee(id, allow_invalid=True)
        if 'badge_type' in params:
            from uber.badge_funcs import reset_badge_if_unchanged
            old_badge_type, old_badge_num = attendee.badge_type, attendee.badge_num
            attendee.badge_type = int(params['badge_type'])
            try:
                attendee.badge_num = int(params['badge_num'])
            except ValueError:
                attendee.badge_num = None

            message = check(attendee)

            if not message:
                message = reset_badge_if_unchanged(attendee, old_badge_type, old_badge_num) or "Badge updated."
                raise HTTPRedirect('form?id={}&message={}', attendee.id, message or '')

        return {
            'message':  message,
            'attendee': attendee
        }

    @unrestricted
    def qrcode_generator(self, data):
        """
        Takes a piece of data, adds the EVENT_QR_ID, and returns an Aztec barcode as an image stream.
        Args:
            data: A string to create a 2D barcode from.

        Returns: A PNG buffer. Use this function in an img tag's src='' to display an image.

        NOTE: this will be called directly by attendee's client browsers to display their 2D barcode.
        This will potentially be called on the order of 100,000 times per event and serve up a lot of data.
        Be sure that any modifications to this code are fast and don't unnecessarily increase CPU load.

        If you run into performance issues, consider using an external cache to cache the results of
        this function.  Or, offload image generation to a dedicated microservice that replicates this functionality.

        """
        checkin_barcode = treepoem.generate_barcode(
            barcode_type='azteccode',
            data=c.EVENT_QR_ID + str(data),
            options={},
        )
        buffer = BytesIO()
        checkin_barcode.save(buffer, "PNG")
        buffer.seek(0)
        png_file_output = cherrypy.lib.file_generator(buffer)

        # set response headers last so that exceptions are displayed properly to the client
        cherrypy.response.headers['Content-Type'] = "image/png"

        return png_file_output

    def history(self, session, id):
        attendee = session.attendee(id, allow_invalid=True)
        return {
            'attendee':  attendee,
            'emails':    session.query(Email)
                                .filter(or_(Email.dest == attendee.email,
                                            and_(Email.model == 'Attendee', Email.fk_id == id)))
                                .order_by(Email.when).all(),
            'changes':   session.query(Tracking)
                                .filter(or_(Tracking.links.like('%attendee({})%'.format(id)),
                                            and_(Tracking.model == 'Attendee', Tracking.fk_id == id)))
                                .order_by(Tracking.when).all(),
            'pageviews': session.query(PageViewTracking).filter(PageViewTracking.what == "Attendee id={}".format(id))
        }

    @log_pageview
    def watchlist(self, session, attendee_id, watchlist_id=None, message='', **params):
        attendee = session.attendee(attendee_id, allow_invalid=True)
        if watchlist_id:
            watchlist_entry = session.watch_list(watchlist_id)

            if 'active' in params:
                watchlist_entry.active = not watchlist_entry.active
            if 'confirm' in params:
                attendee.watchlist_id = watchlist_id
            if 'ignore' in params:
                attendee.badge_status = c.COMPLETED_STATUS

            session.commit()

            message = 'Watchlist entry updated'
        return {
            'attendee': attendee,
            'message': message
        }

    def watchlist_entries(self, session, message='', **params):
        watch_entry = session.watch_list(params, bools=WatchList.all_bools)

        if 'first_names' in params:
            if not watch_entry.first_names or not watch_entry.last_name:
                message = 'First and last name are required.'
            elif not watch_entry.reason or not watch_entry.action:
                message = 'Reason and action are required.'

            if not message:
                session.add(watch_entry)
                if 'id' not in params:
                    message = 'New watch list item added.'
                else:
                    message = 'Watch list item updated.'

                session.commit()

            watch_entry = WatchList()

        return {
            'new_watch': watch_entry,
            'watchlist_entries': session.query(WatchList).order_by(WatchList.last_name).all(),
            'message': message
        }

    def duplicate(self, session, id, return_to='index'):
        attendee = session.attendee(id)
        return {
            'attendee': attendee,
            'return_to': return_to
        }

    @csrf_protected
    def delete(self, session, id, return_to='index?'):
        attendee = session.attendee(id, allow_invalid=True)
        if attendee.group:
            if attendee.group.leader_id == attendee.id:
                message = 'You cannot delete the leader of a group; you must make someone else the leader first, or just delete the entire group'
            elif attendee.is_unassigned:
                session.delete_from_group(attendee, attendee.group)
                message = 'Unassigned badge removed.'
            else:
                replacement_attendee = Attendee(**{attr: getattr(attendee, attr) for attr in [
                    'group', 'registered', 'badge_type', 'badge_num', 'paid', 'amount_paid', 'amount_extra'
                ]})
                if replacement_attendee.group and replacement_attendee.group.is_dealer:
                    replacement_attendee.ribbon = add_opt(replacement_attendee.ribbon_ints, c.DEALER_RIBBON)
                session.add(replacement_attendee)
                session.delete_from_group(attendee, attendee.group)
                message = 'Attendee deleted, but this badge is still available to be assigned to someone else in the same group'
        else:
            session.delete(attendee)
            message = 'Attendee deleted'

        raise HTTPRedirect(return_to + ('' if return_to[-1] == '?' else '&') + 'message={}', message)

    def goto_volunteer_checklist(self, id):
        cherrypy.session['staffer_id'] = id
        raise HTTPRedirect('../signups/index')

    @ajax
    def record_mpoint_cashout(self, session, badge_num, amount):
        try:
            attendee = session.attendee(badge_num=badge_num)
        except:
            return {'success': False, 'message': 'No one has badge number {}'.format(badge_num)}

        mfc = MPointsForCash(attendee=attendee, amount=amount)
        message = check(mfc)
        if message:
            return {'success': False, 'message': message}
        else:
            session.add(mfc)
            session.commit()
            message = '{mfc.attendee.full_name} exchanged {mfc.amount} MPoints for cash'.format(mfc=mfc)
            return {'id': mfc.id, 'success': True, 'message': message}

    @ajax
    def undo_mpoint_cashout(self, session, id):
        session.delete(session.mpoints_for_cash(id))
        return 'MPoint usage deleted'

    @ajax
    def record_old_mpoint_exchange(self, session, badge_num, amount):
        try:
            attendee = session.attendee(badge_num=badge_num)
        except:
            return {'success': False, 'message': 'No one has badge number {}'.format(badge_num)}

        ome = OldMPointExchange(attendee=attendee, amount=amount)
        message = check(ome)
        if message:
            return {'success': False, 'message': message}
        else:
            session.add(ome)
            session.commit()
            message = "{ome.attendee.full_name} exchanged {ome.amount} of last year's MPoints".format(ome=ome)
            return {'id': ome.id, 'success': True, 'message': message}

    @ajax
    def undo_mpoint_exchange(self, session, id):
        session.delete(session.old_m_point_exchange(id))
        session.commit()
        return 'MPoint exchange deleted'

    @ajax
    def record_sale(self, session, badge_num=None, **params):
        params['reg_station'] = cherrypy.session.get('reg_station') or 0
        sale = session.sale(params)
        message = check(sale)
        if not message and badge_num is not None:
            try:
                sale.attendee = session.query(Attendee).filter_by(badge_num=badge_num).one()
            except:
                message = 'No attendee has that badge number'

        if message:
            return {'success': False, 'message': message}
        else:
            session.add(sale)
            session.commit()
            message = '{sale.what} sold{to} for ${sale.cash}{mpoints}' \
                      .format(sale=sale,
                              to=(' to ' + sale.attendee.full_name) if sale.attendee else '',
                              mpoints=' and {} MPoints'.format(sale.mpoints) if sale.mpoints else '')
            return {'id': sale.id, 'success': True, 'message': message}

    @ajax
    def undo_sale(self, session, id):
        session.delete(session.sale(id))
        return 'Sale deleted'

    def check_in_form(self, session, id):
        attendee = session.attendee(id)
        return {
            'attendee': attendee,
            'groups': [
                (group.id, (group.name if len(group.name) < 30 else '{}...'.format(group.name[:27], '...'))
                         + (' ({})'.format(group.leader.full_name) if group.leader else ''))
                for group in session.query(Group)
                                    .options(joinedload(Group.leader))
                                    .filter(Group.status != c.WAITLISTED,
                                            Group.id.in_(
                                                session.query(Attendee.group_id)
                                                       .filter(Attendee.group_id != None, Attendee.first_name == '')
                                                       .distinct().subquery()))
                                    .order_by(Group.name)
            ] if attendee.paid == c.PAID_BY_GROUP and not attendee.group_id else []
        }

    @ajax
    def check_in(self, session, message='', group_id='', **params):
        attendee = session.attendee(params, allow_invalid=True)
        group = attendee.group or (session.group(group_id) if group_id else None)

        pre_badge = attendee.badge_num
        success, increment = False, False

        message = pre_checkin_check(attendee, group)
        if not message and group_id:
            message = session.match_to_group(attendee, group)

        if not message and attendee.paid == c.PAID_BY_GROUP and not attendee.group_id:
            message = 'You must select a group for this attendee.'

        if not message:
            message = ''
            success = True
            attendee.checked_in = sa.localized_now()
            session.commit()
            increment = True
            message += '{} checked in as {}{}'.format(attendee.full_name, attendee.badge, attendee.accoutrements)

        return {
            'success':    success,
            'message':    message,
            'increment':  increment,
            'badge':      attendee.badge,
            'paid':       attendee.paid_label,
            'age_group':  attendee.age_group_conf['desc'],
            'pre_badge':  pre_badge,
            'checked_in': attendee.checked_in and hour_day_format(attendee.checked_in)
        }

    @csrf_protected
    def undo_checkin(self, session, id, pre_badge):
        attendee = session.attendee(id, allow_invalid=True)
        attendee.checked_in, attendee.badge_num = None, pre_badge
        session.add(attendee)
        session.commit()
        return 'Attendee successfully un-checked-in'

    def recent(self, session):
        return {'attendees': session.query(Attendee)
                                    .options(joinedload(Attendee.group))
                                    .order_by(Attendee.registered.desc())
                                    .limit(1000)}

    def merch(self, message=''):
        return {'message': message}

    def multi_merch_pickup(self, session, message="", csrf_token=None, picker_upper=None, badges=(), **shirt_sizes):
        picked_up = []
        if csrf_token:
            check_csrf(csrf_token)
            try:
                picker_upper = session.query(Attendee).filter_by(badge_num=int(picker_upper)).one()
            except:
                message = 'Please enter a valid badge number for the person picking up the merch: {} is not in the system'.format(picker_upper)
            else:
                for badge_num in set(badges):
                    if badge_num:
                        try:
                            attendee = session.query(Attendee).filter_by(badge_num=int(badge_num)).one()
                        except:
                            picked_up.append('{!r} is not a valid badge number'.format(badge_num))
                        else:
                            if attendee.got_merch:
                                picked_up.append('{a.full_name} (badge {a.badge_num}) already got their merch'.format(a=attendee))
                            else:
                                attendee.got_merch = True
                                shirt_key = 'shirt_{}'.format(attendee.badge_num)
                                if shirt_key in shirt_sizes:
                                    attendee.shirt = int(listify(shirt_sizes.get(shirt_key, c.SIZE_UNKNOWN))[0])
                                picked_up.append('{a.full_name} (badge {a.badge_num}): {a.merch}'.format(a=attendee))
                                session.add(MerchPickup(picked_up_by=picker_upper, picked_up_for=attendee))
                session.commit()

        return {
            'message': message,
            'picked_up': picked_up,
            'picker_upper': picker_upper
        }

    def lost_badge(self, session, id):
        a = session.attendee(id, allow_invalid=True)
        a.for_review += "Automated message: Badge reported lost on {}. Previous payment type: {}.".format(localized_now().strftime('%m/%d, %H:%M'), a.paid_label)
        a.paid = c.LOST_BADGE
        session.add(a)
        session.commit()
        raise HTTPRedirect('index?message={}', 'Badge has been recorded as lost.')

    @ajax
    def check_merch(self, session, badge_num):
        id = shirt = None
        if not (badge_num.isdigit() and 0 < int(badge_num) < 99999):
            message = 'Invalid badge number'
        else:
            results = session.query(Attendee).filter_by(badge_num=badge_num)
            if results.count() != 1:
                message = 'No attendee has badge number {}'.format(badge_num)
            else:
                attendee = results.one()
                if not attendee.merch:
                    message = '{a.full_name} ({a.badge}) has no merch'.format(a=attendee)
                elif attendee.got_merch:
                    message = '{a.full_name} ({a.badge}) already got {a.merch}.' \
                              ' Their shirt size is {shirt}'.format(a=attendee, shirt=c.SHIRTS[attendee.shirt])
                else:
                    id = attendee.id
                    shirt = (attendee.shirt or c.SIZE_UNKNOWN) if attendee.gets_any_kind_of_shirt else c.NO_SHIRT
                    message = '{a.full_name} ({a.badge}) has not yet received {a.merch}'.format(a=attendee)
        return {
            'id': id,
            'shirt': shirt,
            'message': message
        }

    @ajax
    def give_merch(self, session, id, shirt_size, no_shirt):
        try:
            shirt_size = int(shirt_size)
        except:
            shirt_size = None

        success = False
        attendee = session.attendee(id, allow_invalid=True)
        if not attendee.merch:
            message = '{} has no merch'.format(attendee.full_name)
        elif attendee.got_merch:
            message = '{} already got {}'.format(attendee.full_name, attendee.merch)
        elif shirt_size == c.SIZE_UNKNOWN:
            message = 'You must select a shirt size'
        else:
            if no_shirt:
                message = '{} is now marked as having received all of the following (EXCEPT FOR THE SHIRT): {}'
            else:
                message = '{} is now marked as having received {}'
            message = message.format(attendee.full_name, attendee.merch)
            attendee.got_merch = True
            if shirt_size:
                attendee.shirt = shirt_size
            if no_shirt:
                session.add(NoShirt(attendee=attendee))
            success = True
            session.commit()

        return {
            'id': id,
            'success': success,
            'message': message
        }

    @ajax
    def take_back_merch(self, session, id):
        attendee = session.attendee(id, allow_invalid=True)
        attendee.got_merch = False
        if attendee.no_shirt:
            session.delete(attendee.no_shirt)
        session.commit()
        return '{a.full_name} ({a.badge}) merch handout canceled'.format(a=attendee)

    @ajax
    def redeem_merch_discount(self, session, badge_num, apply=''):
        try:
            attendee = session.query(Attendee).filter_by(badge_num=badge_num).one()
        except:
            return {'error': 'No attendee exists with that badge number.'}

        if attendee.badge_type != c.STAFF_BADGE:
            return {'error': 'Only staff badges are eligible for discount.'}

        discount = session.query(MerchDiscount).filter_by(attendee_id=attendee.id).first()
        if not apply:
            if discount:
                return {
                    'warning': True,
                    'message': 'This staffer has already redeemed their discount {} time{}'.format(discount.uses, 's' if discount.uses > 1 else '')
                }
            else:
                return {'message': 'Tell staffer their discount is only usable one time and confirm that they want to redeem it.'}

        discount = discount or MerchDiscount(attendee_id=attendee.id, uses=0)
        discount.uses += 1
        session.add(discount)
        session.commit()
        return {'success': True, 'message': 'Discount on badge #{} has been marked as redeemed.'.format(badge_num)}

    @unrestricted
    @check_atd
    def register(self, session, message='', **params):
        params['id'] = 'None'
        attendee = session.attendee(params, restricted=True, ignore_csrf=True)
        if 'first_name' in params:
            if not attendee.payment_method and (not c.BADGE_PRICE_WAIVED or c.BEFORE_BADGE_PRICE_WAIVED):
                message = 'Please select a payment type'
            elif attendee.payment_method == c.MANUAL and not re.match(c.EMAIL_RE, attendee.email):
                message = 'Email address is required to pay with a credit card at our registration desk'
            elif attendee.badge_type not in [badge for badge, desc in c.AT_THE_DOOR_BADGE_OPTS]:
                message = 'No hacking allowed!'
            else:
                message = check(attendee)

            if not message:
                session.add(attendee)
                session.commit()
                message = 'Thanks!  Please queue in the {} line and have your photo ID and {} ready.'
                if c.AFTER_BADGE_PRICE_WAIVED:
                    message = "Since it's so close to the end of the event, your badge is free!  Please proceed to the preregistration line to pick it up."
                    attendee.paid = c.NEED_NOT_PAY
                elif attendee.payment_method == c.STRIPE:
                    raise HTTPRedirect('pay?id={}', attendee.id)
                elif attendee.payment_method == c.GROUP:
                    message = 'Please proceed to the preregistration line to pick up your badge.'
                    attendee.paid = c.PAID_BY_GROUP
                elif attendee.payment_method == c.CASH:
                    message = message.format('cash', '${}'.format(attendee.total_cost))
                elif attendee.payment_method == c.MANUAL:
                    message = message.format('credit card', 'credit card')
                raise HTTPRedirect('register?message={}', message)

        return {
            'message':  message,
            'attendee': attendee
        }

    @unrestricted
    @check_atd
    def pay(self, session, id, message=''):
        attendee = session.attendee(id)
        if attendee.paid != c.NOT_PAID:
            raise HTTPRedirect('register?message={}', 'You are already paid (or registered for a free badge) and should proceed to the preregistration desk to pick up your badge')
        else:
            return {
                'message': message,
                'attendee': attendee,
                'charge': Charge(attendee, description=attendee.full_name)
            }

    @unrestricted
    @check_atd
    @credit_card
    def take_payment(self, session, payment_id, stripeToken):
        charge = Charge.get(payment_id)
        [attendee] = charge.attendees
        message = charge.charge_cc(session, stripeToken)
        if message:
            raise HTTPRedirect('pay?id={}&message={}', attendee.id, message)
        else:
            attendee.paid = c.HAS_PAID
            attendee.amount_paid = attendee.total_cost
            session.merge(attendee)
            raise HTTPRedirect('register?message={}', 'Your payment has been accepted, please proceed to the Preregistration desk to pick up your badge')

    def comments(self, session, order='last_name'):
        return {
            'order': Order(order),
            'attendees': session.query(Attendee).filter(Attendee.comments != '').order_by(order).all()
        }

    def new(self, session, show_all='', message='', checked_in=''):
        if 'reg_station' not in cherrypy.session:
            raise HTTPRedirect('new_reg_station')

        if show_all:
            restrict_to = [Attendee.paid == c.NOT_PAID, Attendee.placeholder == False]
        else:
            restrict_to = [Attendee.paid != c.NEED_NOT_PAY, Attendee.registered > datetime.now(UTC) - timedelta(minutes=90)]

        return {
            'message':    message,
            'show_all':   show_all,
            'checked_in': checked_in,
            'recent':     session.query(Attendee)
                                 .filter(Attendee.checked_in == None,
                                         Attendee.first_name != '',
                                         Attendee.badge_status.in_([c.NEW_STATUS, c.COMPLETED_STATUS]),
                                         *restrict_to)
                                 .order_by(Attendee.registered).all(),
            'Charge': Charge
        }

    def new_reg_station(self, reg_station='', message=''):
        if reg_station:
            if not reg_station.isdigit() or not (0 <= int(reg_station) < 100):
                message = 'Reg station must be a positive integer between 0 and 100'

            if not message:
                cherrypy.session['reg_station'] = int(reg_station)
                raise HTTPRedirect('new?message={}', 'Reg station number recorded')

        return {
            'message': message,
            'reg_station': reg_station
        }

    @ajax
    def mark_as_paid(self, session, id, payment_method):
        if cherrypy.session['reg_station'] == 0:
            return {'success': False, 'message': 'Reg station 0 is for prereg only and may not accept payments'}

        attendee = session.attendee(id)
        attendee.paid = c.HAS_PAID
        if int(payment_method) == c.STRIPE_ERROR:
            attendee.for_review += "Automated message: Stripe payment manually verified by admin."
        attendee.payment_method = payment_method
        attendee.amount_paid = attendee.total_cost
        attendee.reg_station = cherrypy.session['reg_station']
        session.commit()
        return {'success': True, 'message': 'Attendee marked as paid.', 'id': attendee.id}

    @ajax
    @credit_card
    def manual_reg_charge(self, session, payment_id, stripeToken):
        charge = Charge.get(payment_id)
        [attendee] = charge.attendees
        message = charge.charge_cc(session, stripeToken)
        if message:
            return {'success': False, 'message': 'Error processing card: {}'.format(message)}
        else:
            attendee.paid = c.HAS_PAID
            attendee.payment_method = c.MANUAL
            attendee.amount_paid = attendee.total_cost
            session.merge(attendee)
            session.commit()
            return {'success': True, 'message': 'Payment accepted.', 'id': attendee.id}

    @csrf_protected
    def new_checkin(self, session, message='', **params):
        attendee = session.attendee(params, allow_invalid=True)
        group = session.group(attendee.group_id) if attendee.group_id else None

        checked_in = ''
        if 'reg_station' not in cherrypy.session:
            raise HTTPRedirect('new_reg_station')

        message = pre_checkin_check(attendee, group)

        if message:
            session.rollback()
        else:
            if group:
                session.match_to_group(attendee, group)
            attendee.checked_in = sa.localized_now()
            attendee.reg_station = cherrypy.session['reg_station']
            message = '{a.full_name} checked in as {a.badge}{a.accoutrements}'.format(a=attendee)
            checked_in = attendee.id
            session.commit()

        raise HTTPRedirect('new?message={}&checked_in={}', message, checked_in)

    @unrestricted
    def arbitrary_charge_form(self, message='', amount=None, description=''):
        charge = None
        if amount is not None:
            if not amount.isdigit() or not (1 <= int(amount) <= 999):
                message = 'Amount must be a dollar amount between $1 and $999'
            elif not description:
                message = "You must enter a brief description of what's being sold"
            else:
                charge = Charge(amount=100 * int(amount), description=description)

        return {
            'charge': charge,
            'message': message,
            'amount': amount,
            'description': description
        }

    @unrestricted
    @credit_card
    def arbitrary_charge(self, session, payment_id, stripeToken):
        charge = Charge.get(payment_id)
        message = charge.charge_cc(session, stripeToken)
        if message:
            raise HTTPRedirect('arbitrary_charge_form?message={}', message)
        else:
            session.add(ArbitraryCharge(
                amount=charge.dollar_amount,
                what=charge.description,
                reg_station=cherrypy.session.get('reg_station')
            ))
            raise HTTPRedirect('arbitrary_charge_form?message={}', 'Charge successfully processed')

    def reg_take_report(self, session, **params):
        if params:
            start = c.EVENT_TIMEZONE.localize(datetime.strptime('{startday} {starthour}:{startminute}'.format(**params), '%Y-%m-%d %H:%M'))
            end = c.EVENT_TIMEZONE.localize(datetime.strptime('{endday} {endhour}:{endminute}'.format(**params), '%Y-%m-%d %H:%M'))
            sales = session.query(Sale).filter(Sale.reg_station == params['reg_station'],
                                               Sale.when > start, Sale.when <= end).all()
            attendees = session.query(Attendee).filter(Attendee.reg_station == params['reg_station'], Attendee.amount_paid > 0,
                                                       Attendee.registered > start, Attendee.registered <= end).all()
            params['sales'] = sales
            params['attendees'] = attendees
            params['total_cash'] = sum(a.amount_paid for a in attendees if a.payment_method == CASH) \
                                 + sum(s.cash for s in sales if s.payment_method == CASH)
            params['total_credit'] = sum(a.amount_paid for a in attendees if a.payment_method in [c.STRIPE, c.SQUARE, c.MANUAL]) \
                                   + sum(s.cash for s in sales if s.payment_method == c.CREDIT)
        else:
            params['endday'] = localized_now().strftime('%Y-%m-%d')
            params['endhour'] = localized_now().strftime('%H')
            params['endminute'] = localized_now().strftime('%M')

        stations = sorted(filter(bool, Attendee.objects.values_list('reg_station', flat=True).distinct()))
        params['reg_stations'] = stations
        params.setdefault('reg_station', stations[0] if stations else 0)
        return params

    def undo_new_checkin(self, session, id):
        attendee = session.attendee(id, allow_invalid=True)
        if attendee.group:
            session.add(Attendee(group=attendee.group, paid=c.PAID_BY_GROUP, badge_type=attendee.badge_type, ribbon=attendee.ribbon))
        attendee.badge_num = None
        attendee.checked_in = attendee.group = None
        raise HTTPRedirect('new?message={}', 'Attendee un-checked-in')

    def shifts(self, session, id, shift_id='', message=''):
        attendee = session.attendee(id, allow_invalid=True)
        return {
            'message':  message,
            'shift_id': shift_id,
            'attendee': attendee,
            'shifts':   Shift.dump(attendee.shifts),
            'jobs':     [(job.id, '({}) [{}] {}'.format(job.timespan(), job.location_label, job.name))
                         for job in session.query(Job)
                                           .outerjoin(Job.shifts)
                                           .filter(Job.location.in_(attendee.assigned_depts_ints),
                                                   or_(Job.restricted == False, Job.location.in_(attendee.trusted_depts_ints)))
                                           .group_by(Job.id)
                                           .having(func.count(Shift.id) < Job.slots)
                                           .order_by(Job.start_time, Job.location)
                         if job.start_time + timedelta(hours=job.duration + 2) > localized_now()]
        }

    @csrf_protected
    def update_nonshift(self, session, id, nonshift_hours):
        attendee = session.attendee(id, allow_invalid=True)
        if not re.match('^[0-9]+$', nonshift_hours):
            raise HTTPRedirect('shifts?id={}&message={}', attendee.id, 'Invalid integer')
        else:
            attendee.nonshift_hours = int(nonshift_hours)
            raise HTTPRedirect('shifts?id={}&message={}', attendee.id, 'Non-shift hours updated')

    @csrf_protected
    def update_notes(self, session, id, admin_notes, for_review=None):
        attendee = session.attendee(id, allow_invalid=True)
        attendee.admin_notes = admin_notes
        if for_review is not None:
            attendee.for_review = for_review
        raise HTTPRedirect('shifts?id={}&message={}', id, 'Admin notes updated')

    @csrf_protected
    def assign(self, session, staffer_id, job_id):
        message = session.assign(staffer_id, job_id) or 'Shift added'
        raise HTTPRedirect('shifts?id={}&message={}', staffer_id, message)

    @csrf_protected
    def unassign(self, session, shift_id):
        shift = session.shift(shift_id)
        session.delete(shift)
        raise HTTPRedirect('shifts?id={}&message={}', shift.attendee.id, 'Staffer unassigned from shift')

    def feed(self, session, message='', page='1', who='', what='', action=''):
        feed = session.query(Tracking).filter(Tracking.action != c.AUTO_BADGE_SHIFT).order_by(Tracking.when.desc())
        what = what.strip()
        if who:
            feed = feed.filter_by(who=who)
        if what:
            like = '%' + what + '%'  # SQLAlchemy should have an icontains for this
            feed = feed.filter(or_(Tracking.data.ilike(like), Tracking.which.ilike(like)))
        if action:
            feed = feed.filter_by(action=action)
        return {
            'message': message,
            'who': who,
            'what': what,
            'page': page,
            'action': action,
            'count': feed.count(),
            'feed': get_page(page, feed),
            'action_opts': [opt for opt in c.TRACKING_OPTS if opt[0] != c.AUTO_BADGE_SHIFT],
            'who_opts': [who for [who] in session.query(Tracking).distinct().order_by(Tracking.who).values(Tracking.who)]
        }

    @csrf_protected
    def undo_delete(self, session, id, message='', page='1', who='', what='', action=''):
        if cherrypy.request.method == "POST":
            model_class = None
            tracked_delete = session.query(Tracking).get(id)
            if tracked_delete.action != c.DELETED:
                message = 'Only a delete can be undone'
            else:
                model_class = Session.resolve_model(tracked_delete.model)

            if model_class:
                params = json.loads(tracked_delete.snapshot)
                model_id = params.get('id').strip()
                if model_id:
                    existing_model = session.query(model_class).filter(
                        model_class.id == model_id).first()
                    if existing_model:
                        message = '{} has already been undeleted'.format(tracked_delete.which)
                    else:
                        model = model_class(id=model_id).apply(params, restricted=False)
                else:
                    model = model_class().apply(params, restricted=False)

                if not message:
                    session.add(model)
                    message = 'Successfully undeleted {}'.format(tracked_delete.which)
            else:
                message = 'Could not resolve {}'.format(tracked_delete.model)

        raise HTTPRedirect('feed?page={}&who={}&what={}&action={}&message={}', page, who, what, action, message)

    def staffers(self, session, message='', order='first_name'):
        staffers = session.staffers().all()
        return {
            'order': Order(order),
            'message': message,
            'taken_hours': sum([s.weighted_hours - s.nonshift_hours for s in staffers], 0.0),
            'total_hours': sum([j.weighted_hours * j.slots for j in session.query(Job).all()], 0.0),
            'staffers': sorted(staffers, reverse=order.startswith('-'), key=lambda s: getattr(s, order.lstrip('-')))
        }

    def review(self, session):
        return {'attendees': session.query(Attendee)
                                    .filter(Attendee.for_review != '')
                                    .order_by(Attendee.full_name).all()}

    @site_mappable
    def discount(self, session, message='', **params):
        attendee = session.attendee(params)
        if 'first_name' in params:
            try:
                if not attendee.first_name or not attendee.last_name:
                    message = 'First and Last Name are required'
                elif attendee.overridden_price < 0:
                    message = 'Non-Negative Discounted Price is required'
                elif attendee.overridden_price > c.BADGE_PRICE:
                    message = 'You cannot create a discounted badge that costs more than the regular price!'
                elif attendee.overridden_price == 0:
                    attendee.paid = c.NEED_NOT_PAY
                    attendee.overridden_price = c.BADGE_PRICE
            except TypeError:
                message = 'Discounted Price is required'

            if not message:
                session.add(attendee)
                attendee.placeholder = True
                attendee.badge_type = c.ATTENDEE_BADGE
                raise HTTPRedirect('../preregistration/confirm?id={}', attendee.id)

        return {'message': message}

    def placeholders(self, session, department=''):
        return {
            'department': department,
            'dept_name': c.JOB_LOCATIONS[int(department)] if department else 'All',
            'checklist': session.checklist_status('placeholders', department),
            'placeholders': [a for a in session.query(Attendee)
                                               .filter(Attendee.placeholder == True,
                                                       Attendee.staffing == True,
                                                       Attendee.badge_status.in_([c.NEW_STATUS, c.COMPLETED_STATUS]),
                                                       Attendee.assigned_depts.contains(department))
                                               .order_by(Attendee.full_name).all()]
        }

    def inactive(self, session):
        return {
            'attendees': session.query(Attendee)
                                .filter(~Attendee.badge_status.in_([c.NEW_STATUS, c.COMPLETED_STATUS]))
                                .order_by(Attendee.badge_status, Attendee.full_name).all()
        }

    @unrestricted
    def stats(self):
        cherrypy.response.headers["Access-Control-Allow-Origin"] = "*"
        return json.dumps({
            'badges_sold': c.BADGES_SOLD,
            'remaining_badges': c.REMAINING_BADGES,
            'badges_price': c.BADGE_PRICE,
            'server_current_timestamp': int(datetime.utcnow().timestamp()),
            'warn_if_server_browser_time_mismatch': c.WARN_IF_SERVER_BROWSER_TIME_MISMATCH
        })

    @unrestricted
    def price(self):
        cherrypy.response.headers["Access-Control-Allow-Origin"] = "*"
        return json.dumps({
            'badges_price': c.BADGE_PRICE
        })
