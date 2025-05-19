from models.db_setup import Base, engine

# Create all tables
Base.metadata.create_all(engine)

print("✅ All tables created successfully!")
