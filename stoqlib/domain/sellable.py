# -*- coding: utf-8 -*-
# vi:si:et:sw=4:sts=4:ts=4

##
## Copyright (C) 2005-2007 Async Open Source <http://www.async.com.br>
## All rights reserved
##
## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU Lesser General Public License as published by
## the Free Software Foundation; either version 2 of the License, or
## (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU Lesser General Public License for more details.
##
## You should have received a copy of the GNU Lesser General Public License
## along with this program; if not, write to the Free Software
## Foundation, Inc., or visit: http://www.gnu.org/.
##
## Author(s):   Evandro Vale Miquelito      <evandro@async.com.br>
##              Johan Dahlin                <jdahlin@async.com.br>
##
""" This module implements base classes to 'sellable objects', such a product
or a service, implemented in your own modules.
"""

import datetime
from decimal import Decimal

from kiwi.datatypes import currency
from sqlobject import DateTimeCol, UnicodeCol, IntCol, ForeignKey, SQLObject
from sqlobject.sqlbuilder import AND, IN, OR
from stoqdrivers.enum import TaxType
from zope.interface import implements

from stoqlib.database.columns import PriceCol, DecimalCol
from stoqlib.database.runtime import get_connection
from stoqlib.domain.interfaces import ISellable, IContainer, IDescribable
from stoqlib.domain.base import (Domain, InheritableModelAdapter,
                                 InheritableModel, BaseSQLView)
from stoqlib.exceptions import (DatabaseInconsistency, SellableError,
                                BarcodeDoesNotExists)
from stoqlib.lib.parameters import sysparam
from stoqlib.lib.translation import stoqlib_gettext
from stoqlib.lib.validators import is_date_in_interval

_ = stoqlib_gettext

#
# Base Domain Classes
#

class SellableUnit(Domain):
    """ A class used to represent the sellable unit.

    @cvar description: The unit description
    @cvar unit_index:  This column defines if this object represents a custom
      product unit (created by the user through the product editor) or
      a 'native unit', like 'Km', 'Lt' and 'pc'.
      This data is used mainly to interact with stoqdrivers, since when adding
      an item in a coupon we need to know if its unit must be specified as
      a description (using CUSTOM_PM constant) or as an index (using UNIT_*).
      Also, this is directly related to the DeviceSettings editor.
    """
    _inheritable = False
    description = UnicodeCol()
    unit_index = IntCol()

class SellableTaxConstant(Domain):
    """
    A tax constant tied to a sellable
    """
    implements(IDescribable)

    description = UnicodeCol()
    tax_type = IntCol()
    tax_value = DecimalCol(default=None)

    _mapping = {
        int(TaxType.NONE): 'TAX_NONE',
        int(TaxType.EXEMPTION): 'TAX_EXEMPTION',
        int(TaxType.SUBSTITUTION): 'TAX_SUBSTITUTION',
        int(TaxType.SERVICE): 'TAX_SERVICE',
        }

    def get_value(self):
        return SellableTaxConstant._mapping.get(
            self.tax_type, self.tax_value)


    @classmethod
    def get_by_type(cls, tax_type, conn):
        """
        Fetch the tax constant for tax_type
        @param tax_type: the tax constant to fetch
        @param conn: a database connection
        @returns: a L{SellableTaxConstant} or None if none is found
        """
        return SellableTaxConstant.selectOneBy(
            tax_type=int(tax_type),
            connection=conn)

    # IDescribable

    def get_description(self):
        return self.description


class SellableCategory(Domain):
    """ Sellable category. This class can represents a
    sellable's category as well its base category.

    @cvar description: The category description
    @cvar suggested_markup: Define the suggested markup when calculating the
       sellable's price.
    @cvar salesperson_comission: A percentage comission suggested for all the
       sales which products belongs to this category.
    @cvar category: base category of this category, None for base categories
       themselves
    """

    description = UnicodeCol()
    suggested_markup = DecimalCol(default=0)
    salesperson_commission = DecimalCol(default=0)
    category = ForeignKey('SellableCategory', default=None)

    implements(IDescribable)

    def get_commission(self):
        """
        Returns the commission for this category.
        If it's unset, return the value of the base category, if any
        @returns: the commission
        """
        if self.category:
            return (self.salesperson_commission or
                    self.category.get_commission())
        return self.salesperson_commission

    def get_markup(self):
        """
        Returns the markup for this category.
        If it's unset, return the value of the base category, if any
        @returns: the markup
        """
        if self.category:
            return self.suggested_markup or self.category.get_markup()
        return self.suggested_markup

    # FIXME: Remove?
    def get_description(self):
        return self.description

    def get_full_description(self):
        if self.category:
            return ("%s %s"
                    % (self.category.get_description(), self.description))
        return self.description

    #
    # Classmethods
    #

    @classmethod
    def get_base_categories(cls, conn):
        """
        Returns all available base categories
        @param conn: a database connection
        @returns: categories
        """
        return cls.select(cls.q.categoryID == None, connection=conn)

class ASellableItem(InheritableModel):
    """Abstract representation of a concrete sellable."""

    quantity = DecimalCol()
    base_price = PriceCol()
    price = PriceCol()
    sale = ForeignKey('Sale')
    sellable = ForeignKey('ASellable')

    def _create(self, id, **kw):
        if not 'kw' in kw:
            if not 'sellable' in kw:
                raise TypeError('You must provide a sellable argument')
            base_price = kw['sellable'].price
            kw['base_price'] = base_price
        InheritableModel._create(self, id, **kw)

    def sell(self):
        self.sellable.sell()

    def cancel(self, branch):
        self.sellable.can_sell()

    #
    # Accessors
    #

    def get_total(self):
        return currency(self.price * self.quantity)

    def get_quantity_unit_string(self):
        return "%s %s" % (self.quantity, self.sellable.get_unit_description())


class OnSaleInfo(Domain):
    _inheritable = False
    on_sale_price = PriceCol(default=0)
    on_sale_start_date = DateTimeCol(default=None)
    on_sale_end_date = DateTimeCol(default=None)


class BaseSellableInfo(Domain):
    implements(IDescribable)

    _inheritable = False
    price = PriceCol(default=0)
    description = UnicodeCol(default='')
    max_discount = DecimalCol(default=0)
    commission = DecimalCol(default=0)

    def get_commission(self):
        return self.commission

    #
    # IDescribable implementation
    #

    def get_description(self):
        return self.description



class ASellable(InheritableModelAdapter):
    """A sellable (a product or a service, for instance)."""

    implements(ISellable, IContainer, IDescribable)

    sellableitem_table = None
    (STATUS_AVAILABLE,
     STATUS_SOLD,
     STATUS_CLOSED,
     STATUS_BLOCKED) = range(4)


    statuses = {STATUS_AVAILABLE:   _(u"Available"),
                STATUS_SOLD:        _(u"Sold"),
                STATUS_CLOSED:      _(u"Closed"),
                STATUS_BLOCKED:     _(u"Blocked")}

    barcode = UnicodeCol(default='')
    # This default status is used when a new sellable is created,
    # so it must be *always* SOLD (that means no stock for it).
    status = IntCol(default=STATUS_SOLD)
    cost = PriceCol(default=0)
    notes = UnicodeCol(default='')
    unit = ForeignKey("SellableUnit", default=None)
    base_sellable_info = ForeignKey('BaseSellableInfo')
    on_sale_info = ForeignKey('OnSaleInfo')
    category = ForeignKey('SellableCategory', default=None)
    tax_constant = ForeignKey('SellableTaxConstant', default=None)

    def _create(self, id, **kw):
        markup = None
        if not 'kw' in kw:
            conn = self.get_connection()
            if not 'on_sale_info' in kw:
                kw['on_sale_info'] = OnSaleInfo(connection=conn)
            # markup specification must to reflect in the sellable price, since
            # there is no such column -- but we can only change the price right
            # after InheritableModelAdapter._create() get executed.
            markup = kw.pop('markup', None)
        InheritableModelAdapter._create(self, id, **kw)
        # I'm not checking price in 'kw' because it can be specified through
        # base_sellable_info, and then we'll not update the price properly;
        # instead, I check for "self.price" that, at this point (after
        # InheritableModelAdapter._create excecution) is already set and
        # accessible through ASellable's price's accessor.
        if not self.price and ('cost' in kw and 'category' in kw):
            markup = markup or kw['category'].get_markup()
            cost = kw.get('cost', currency(0))
            self.price = cost * (markup / currency(100) + 1)
        if not self.commission and self.category:
            self.commission = self.category.get_commission()

    #
    # SQLObject setters
    #

    def _set_barcode(self, barcode):
        if ASellable.check_barcode_exists(barcode):
            raise SellableError("The barcode %s already exists" % barcode)
        self._SO_set_barcode(barcode)

    #
    # Helper methods
    #

    def _get_price_by_markup(self, markup):
        return self.cost + (self.cost * (markup / currency(100)))

    def _get_status_string(self):
        if not self.statuses.has_key(self.status):
            raise DatabaseInconsistency('Invalid status for product got '
                                        '%d' % self.status)
        return self.statuses[self.status]

    #
    # Properties
    #

    def _get_markup(self):
        if self.cost == 0:
            return Decimal(0)
        return ((self.price / self.cost) - 1) * 100

    def _set_markup(self, markup):
        self.price = self._get_price_by_markup(markup)

    markup = property(_get_markup, _set_markup)

    def _get_price(self):
        if self.on_sale_info.on_sale_price:
            today = datetime.datetime.today()
            start_date = self.on_sale_info.on_sale_start_date
            end_date = self.on_sale_info.on_sale_end_date
            if is_date_in_interval(today, start_date, end_date):
                return self.on_sale_info.on_sale_price
        return self.base_sellable_info.price

    def _set_price(self, price):
        self.base_sellable_info.price = price

    price = property(_get_price, _set_price)

    def _get_commission(self):
        return self.base_sellable_info.get_commission()

    def _set_commission(self, commission):
        self.base_sellable_info.commission = commission

    commission = property(_get_commission, _set_commission)

    @property
    def code(self):
        return self.id


    #
    # IContainer methods
    #

    def add_item(self, item):
        raise NotImplementedError(
            "You should call add_sellable_item instead")

    def get_items(self):
        if not self.sellableitem_table:
            raise TypeError("Subclasses must provide a sellableitem_table"
                            " attribute")

        return self.sellableitem_table.selectBy(
            sellable=self, connection=self.get_connection())

    def remove_item(self, item):
        if not self.sellableitem_table:
            raise TypeError("Subclasses must provide a sellableitem_table"
                            " attribute")
        conn = self.get_connection()
        if not isinstance(item, self.sellableitem_table):
            raise TypeError("Item should be of type %s, got "
                            % (self.sellableitem_table, type(item)))
        self.sellableitem_table.delete(item.id, connection=conn)

    #
    # ISellable methods
    #

    def can_be_sold(self):
        return self.status == self.STATUS_AVAILABLE

    def is_sold(self):
        return self.status == self.STATUS_SOLD

    def sell(self):
        if self.is_sold():
            raise ValueError('This sellable is already sold')
        self.status = self.STATUS_SOLD

    def cancel(self):
        if self.can_be_sold():
            raise ValueError('This sellable is already available')
        self.status = self.STATUS_AVAILABLE

    def can_sell(self):
        # Identical implementation to cancel(), but it has a very different
        # use case, so we keep another method
        self.status = self.STATUS_AVAILABLE

    def add_sellable_item(self, sale, quantity=1, price=None, **kwargs):
        """Add a new sellable item instance tied to the current
        sellable object
        """
        if not self.sellableitem_table:
            raise ValueError('Child classes must define a sellableitem_table '
                             'attribute')
        price = price or self.price
        conn = self.get_connection()
        return self.sellableitem_table(connection=conn, quantity=quantity,
                                       sale=sale, sellable=self,
                                       price=price, **kwargs)
    def get_code_str(self):
        return u"%05d" % self.id

    def get_short_description(self):
        return u'%s %s' % (self.id, self.base_sellable_info.description)

    def get_suggested_markup(self):
        return self.category and self.category.get_markup()

    def get_unit_description(self):
        return self.unit and self.unit.description or u""

    #
    # IDescribable implementation
    #

    def get_description(self):
        return self.base_sellable_info.get_description()

    #
    # Classmethods
    #

    @classmethod
    def check_barcode_exists(cls, barcode):
        """Returns True if we already have a sellable with the given barcode
        in the database.
        """
        if not barcode:
            return False
        conn = get_connection()
        # XXX Do not use cls instead of ASellable here since SQLObject
        # can deal properly with queries in inherited tables in this case
        results = ASellable.selectBy(barcode=barcode, connection=conn)
        return results.count()

    @classmethod
    def get_available_sellables_query(cls, conn):
        service = sysparam(conn).DELIVERY_SERVICE
        return AND(cls.q.id != service.id,
                   cls.q.status == cls.STATUS_AVAILABLE)

    @classmethod
    def get_available_sellables(cls, conn):
        """Returns sellable objects which can be added in a sale. By
        default a delivery sellable can not be added manually by users
        since a separated dialog is responsible for that.
        """
        query = cls.get_available_sellables_query(conn)
        return cls.select(query, connection=conn)

    @classmethod
    def get_unblocked_sellables(cls, conn, storable=False):
        """
        @param conn: a database connection
        @param storable: if True, only return Storables
        """
        query = OR(cls.get_available_sellables_query(conn),
                   cls.q.status == cls.STATUS_SOLD)
        if storable:
            from stoqlib.domain.product import (Product, ProductAdaptToSellable,
                                                ProductAdaptToStorable)
            query = AND(query,
                        ProductAdaptToSellable.q.id == cls.q.id,
                        ProductAdaptToSellable.q._originalID == Product.q.id,
                        ProductAdaptToStorable.q._originalID == Product.q.id)

        return cls.select(query, connection=conn)

    @classmethod
    def get_sold_sellables(cls, conn):
        """Returns sellable objects which can be added in a sale. By
        default a delivery sellable can not be added manually by users
        since a separated dialog is responsible for that.
        """
        return cls.selectBy(status=cls.STATUS_SOLD, connection=conn)

    @classmethod
    def _get_sellables_by_barcode(cls, conn, barcode, extra_query):
        sellable = cls.selectOne(
            AND(ASellable.q.barcode == barcode,
                extra_query), connection=conn)
        if sellable is None:
            raise BarcodeDoesNotExists(
                _("The sellable with barcode '%s' doesn't exists or is "
                  "not available to be sold" % barcode))
        return sellable

    @classmethod
    def get_availables_by_barcode(cls, conn, barcode):
        """Returns a list of avaliable sellables that can be sold.
        A sellable that can be sold can have only one possible
        status: STATUS_AVAILABLE

        @param conn: a sqlobject Transaction instance
        @param barcode: a string representing a sellable barcode
        """
        return cls._get_sellables_by_barcode(
            conn, barcode,
            ASellable.q.status == ASellable.STATUS_AVAILABLE)

    @classmethod
    def get_availables_and_sold_by_barcode(cls, conn, barcode):
        """Returns a list of avaliable sellables and also sellables that
        can be sold.  Here we will get sellables with the following
        statuses: STATUS_AVAILABLE, STATUS_SOLD

        @param conn: a sqlobject Transaction instance
        @param barcode: a string representing a sellable barcode
        """
        statuses = [cls.STATUS_AVAILABLE, cls.STATUS_SOLD]
        return cls._get_sellables_by_barcode(conn, barcode,
                                             IN(cls.q.status, statuses))

#
# Views
#


class SellableView(SQLObject, BaseSQLView):
    """Stores general sellable informations and stock for all branch
    companies
    """
    stock = DecimalCol()
    barcode = UnicodeCol()
    status = IntCol()
    cost = PriceCol()
    price = PriceCol()
    description = UnicodeCol()
    supplier_name = UnicodeCol()
    unit = UnicodeCol()
    branch_id = IntCol()
    product_id = IntCol()

    def get_supplier_name(self):
        return self.supplier_name or u""

    def get_unit(self):
        return self.unit or u""


class SellableFullStockView(SellableView):
    """Stores the total stock in all branch companies and other general
    informations for sellables
    """
