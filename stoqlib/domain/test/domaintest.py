# -*- coding: utf-8 -*-
# vi:si:et:sw=4:sts=4:ts=4

##
## Copyright (C) 2006-2007 Async Open Source <http://www.async.com.br>
## All rights reserved
##
## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation; either version 2 of the License, or
## (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with this program; if not, write to the Free Software
## Foundation, Inc., or visit: http://www.gnu.org/.
##
## Author(s): Stoq Team <stoq-devel@async.com.br>
##
""" Base module to be used by all domain test modules"""

from stoqlib.lib.kiwilibrary import library
library  # pyflakes

from stoqlib.database.runtime import (get_current_branch,
                                      new_transaction)
from stoqlib.domain.exampledata import ExampleCreator

try:
    import unittest
    unittest # pyflakes
except:
    import unittest


class DomainTest(unittest.TestCase, ExampleCreator):
    def __init__(self, test):
        unittest.TestCase.__init__(self, test)
        ExampleCreator.__init__(self)

    def setUp(self):
        self.trans = new_transaction()
        self.set_transaction(self.trans)

    def tearDown(self):
        self.trans.rollback()
        self.clear()

    def collect_sale_models(self, sale):
        models = [sale,
                  sale.group]
        models.extend(sale.payments)
        branch = get_current_branch(self.trans)
        for item in sorted(sale.get_items(),
                           cmp=lambda a, b: cmp(a.sellable.description,
                                                b.sellable.description)):
            models.append(item.sellable)
            stock_item = item.sellable.product_storable.get_stock_item(branch)
            models.append(stock_item)
            models.append(item)
        p = list(sale.payments)[0]
        p.description = p.description.rsplit(' ', 1)[0]
        return models
